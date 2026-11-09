"""Bounded worker path; all model doubles explicitly fixture-classified in receipts."""

from __future__ import annotations

import copy
import json
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from threading import Barrier

import pytest

from queen_os.authority import AuthorityError, Grant
from queen_os.cli import main
from queen_os.comb.capsule import (
    CapsuleError,
    StaleCapsule,
    build_capsule,
    verify_capsule,
    verify_recorded_capsule,
)
from queen_os.comb.projection import fold_eggs
from queen_os.gate.gate import Gate
from queen_os.hive import Hive
from queen_os.providers import FixtureProvider
from queen_os.providers.receipt import Inference, StructuredOutputRejected
from queen_os.queen import planner
from queen_os.queen.egg import lay
from queen_os.queen.run_budget import RunBudget
from queen_os.serial.jcs import canonicalize
from queen_os.workers import execution as ex
from queen_os.workers.claim import ResumeBlocked, Worker

NOTES = {"a": "Item apple; quantity 2.", "b": "Item pear; quantity 3."}
ITEMS = [{"source_id": "a", "item": "apple", "quantity": 2}, {"source_id": "b", "item": "pear", "quantity": 3}]
PROPOSAL = {
    "v": 1,
    "tasks": [
        {"id": "a", "kind": "extract_items", "source_id": "a", "parents": []},
        {"id": "b", "kind": "extract_items", "source_id": "b", "parents": []},
        {"id": "c", "kind": "combine_items", "source_id": "", "parents": ["a", "b"]},
    ],
}


@pytest.fixture
def hive(tmp_path):
    with Hive.init(tmp_path / "h", "worker", mode="test") as h:
        yield h


def publish(h, goal="goal", notes=None):
    p = FixtureProvider("fixture_workers", [json.dumps(PROPOSAL)])
    planner.prepare(h, goal, "Extract exact items and combine.", notes or NOTES, RunBudget(), p, "m")
    planner.generate(h, goal, p)
    return planner.publish(h, goal)


def prepared(h):
    publish(h)
    return ex.prepare_next(h, "goal", "nurse")


def fit(h, event, **changes):
    proof = {
        "v": 1,
        "request_sha256": event.payload["request_sha256"],
        "model": "m",
        "provider_kind": "fixture",
        "context_tokens": 2048,
        "prompt_tokens": 200,
        "schema_tokens": 100,
        "method": "operator_backend_tokenizer",
    }
    proof.update(changes)
    return ex.ContextFit(
        proof["context_tokens"], proof["prompt_tokens"], proof["schema_tokens"], h.blobs.put(canonicalize(proof))
    )


def reply(event):
    # Host expected values are used only for the explicitly classified test double.
    context_input = event.payload["egg_id"]
    assert context_input.startswith("egg_")
    return {"items": [ITEMS[0]]}


def infer(h, event, output=None):
    return ex.generate(
        h,
        event.payload["egg_id"],
        "nurse",
        fit(h, event),
        FixtureProvider("fixture_workers", [json.dumps(reply(event) if output is None else output)]),
    )


def test_goal_filter_precedes_any_lease_capability_or_purge(hive):
    plan = publish(hive)
    other = lay(hive, "unrelated", "diploid", {"data": "unrelated"}, planner._ITEM_SCHEMA, stimulus=1.0)
    event = ex.prepare_next(hive, "goal", "nurse")
    assert event.payload["egg_id"] in {e.egg_id for e in plan.eggs}
    assert fold_eggs(hive.ledger)[other.egg_id].state == "laid"
    assert hive.ledger._db.execute("SELECT 1 FROM leases WHERE resource=?", ("egg:" + other.egg_id,)).fetchone() is None
    assert not [e for e in hive.ledger.events(kind="capability.issued") if e.payload["scope"] == "egg:" + other.egg_id]


@pytest.mark.parametrize("bad", ["", "../goal", "x" * 65, 1, True])
def test_bad_goal_filter_has_no_effect(hive, bad):
    before = hive.ledger.head()
    with pytest.raises(ValueError):
        Worker(hive, "nurse", goal_id=bad)
    assert hive.ledger.head() == before


def test_recorded_capsule_replays_prefix_but_cannot_resume(hive):
    event = prepared(hive)
    capsule = hive.blobs.get(event.payload["capsule_sha256"])
    assert verify_recorded_capsule(hive, capsule).raw == capsule
    with pytest.raises(StaleCapsule):
        verify_capsule(hive, capsule)
    with pytest.raises(StaleCapsule):
        Worker(hive, "nurse", goal_id="goal").resume(capsule)
    value = json.loads(capsule)
    value["task"]["input"]["source"]["text"] = "Item gold; quantity 999."
    with pytest.raises(CapsuleError):
        verify_recorded_capsule(hive, canonicalize(value))
    value = json.loads(capsule)
    value["head"]["hash"] = "0" * 64
    with pytest.raises(CapsuleError):
        verify_recorded_capsule(hive, canonicalize(value))


def test_capsule_request_omits_bookkeeping_and_has_exact_native_schema(hive):
    event = prepared(hive)
    _, request = ex.preview(hive, event.payload["egg_id"])
    data = json.loads(request.messages[0].content)
    assert set(data) == {"task", "accepted_parents"} and data["accepted_parents"] == []
    assert request.output.schema == planner._ITEM_SCHEMA and request.max_tokens == 512
    assert request.temperature == 0 and "lease" not in data and "signature" not in data


def test_known_receipt_restores_live_claim_without_minting_or_inference(hive):
    event = prepared(hive)
    receipt = infer(hive, event)
    before = hive.ledger.head()
    w = Worker(hive, "nurse", goal_id="goal", providers=("fixture_workers",), models=("m",))
    restored = w.recover_receipt(event.payload["egg_id"], receipt.seq)
    assert restored.capability.token_id == event.payload["token_id"]
    assert hive.ledger.head() == before
    with pytest.raises(ResumeBlocked):
        w.resume(build_capsule(hive, event.payload["egg_id"]).raw)
    decision = ex.recover(hive, event.payload["egg_id"], receipt.seq, "nurse")
    assert decision.verdict == "hatched"
    assert len(list(hive.ledger.events(kind="capability.spent"))) == 2  # one planner, one worker


@pytest.mark.parametrize("fault", ["expired", "revoked", "different_actor", "different_goal", "wrong_receipt"])
def test_known_receipt_cannot_restore_wrong_or_dead_claim(hive, monkeypatch, fault):
    event = prepared(hive)
    receipt = infer(hive, event)
    if fault == "expired":
        monkeypatch.setattr(hive.ledger, "now", lambda: event.payload["lease_expires_ms"] + 1)
    if fault == "revoked":
        hive.authority().revoke(event.payload["token_id"], "test")
    w = Worker(
        hive,
        "other" if fault == "different_actor" else "nurse",
        goal_id="other" if fault == "different_goal" else "goal",
        providers=("fixture_workers",),
        models=("m",),
    )
    before = hive.ledger.head()
    with pytest.raises((AuthorityError, ResumeBlocked)):
        w.recover_receipt(event.payload["egg_id"], receipt.seq + (1 if fault == "wrong_receipt" else 0))
    assert hive.ledger.head() == before


@pytest.mark.parametrize("phase", ["receipt_return", "staging_return", "delivery_return"])
def test_interrupted_known_effect_recovers_by_readback_without_repeating_it(hive, monkeypatch, phase):
    event = prepared(hive)
    original = hive.ledger._post_write_fetch
    if phase == "receipt_return":

        def lost(seq):
            e = original(seq)
            if e.kind == "inference.receipt":
                raise OSError("receipt committed; return lost")
            return e

        monkeypatch.setattr(hive.ledger, "_post_write_fetch", lost)
        with pytest.raises(OSError):
            infer(hive, event)
        monkeypatch.setattr(hive.ledger, "_post_write_fetch", original)
    else:
        infer(hive, event)
    receipt = list(hive.ledger.events(kind="inference.receipt"))[-1]
    if phase == "staging_return":
        stage = type(hive.enclaves).stage

        def lost_stage(self, name, data):
            stage(self, name, data)
            raise OSError("staging write committed; return lost")

        monkeypatch.setattr(type(hive.enclaves), "stage", lost_stage)
        with pytest.raises(OSError):
            ex.recover(hive, event.payload["egg_id"], receipt.seq, "nurse")

        def forbid_stage(*_):
            pytest.fail("recovery repeated staging effect")

        monkeypatch.setattr(type(hive.enclaves), "stage", forbid_stage)
    if phase == "delivery_return":

        def lost_delivery(seq):
            e = original(seq)
            if e.kind == "egg.delivered":
                raise OSError("delivery committed; return lost")
            return e

        monkeypatch.setattr(hive.ledger, "_post_write_fetch", lost_delivery)
        with pytest.raises(OSError):
            ex.recover(hive, event.payload["egg_id"], receipt.seq, "nurse")
        monkeypatch.setattr(hive.ledger, "_post_write_fetch", original)
    assert ex.recover(hive, event.payload["egg_id"], receipt.seq, "nurse").verdict == "hatched"
    before = len(list(hive.ledger.events(kind="egg.delivered")))
    assert ex.recover(hive, event.payload["egg_id"], receipt.seq, "nurse").verdict == "hatched"
    assert len(list(hive.ledger.events(kind="egg.delivered"))) == before == 1
    assert len(list(hive.ledger.events(kind="capability.spent"))) == 2


def test_unknown_transport_stays_spent_and_replacement_cap_cannot_retry(hive, monkeypatch):
    event = prepared(hive)
    provider = FixtureProvider("fixture_workers", [])

    def unknown(*_, **kwargs):
        raise OSError("unknown external outcome")

    monkeypatch.setattr(provider, "send", unknown)
    with pytest.raises(OSError):
        ex.generate(hive, event.payload["egg_id"], "nurse", fit(hive, event), provider)
    state = ex.inspect(hive, "goal")
    assert state["tasks"][0]["effect"] == "UNKNOWN_AFTER_SPEND"
    with pytest.raises(ResumeBlocked):
        infer(hive, event)
    with pytest.raises(ex.ExecutionError):
        ex.prepare_next(hive, "goal", "nurse")
    cap = hive.authority().issue(
        "worker:nurse",
        "egg:" + event.payload["egg_id"],
        Grant(providers=("fixture_workers",), models=("m",), max_calls=1, max_output_tokens=512),
        60_000,
    )
    with pytest.raises(AuthorityError):
        hive.authority().authorize_inference(cap, "worker:nurse", "fixture_workers", "m", 512)
    assert len(list(hive.ledger.events(kind="capability.spent"))) == 2


@pytest.mark.parametrize("change", ["source", "item", "quantity", "missing", "extra", "duplicate"])
def test_schema_valid_wrong_output_is_quarantined_not_repaired(hive, change):
    event = prepared(hive)
    output = copy.deepcopy(reply(event))
    if change in {"source", "item", "quantity"}:
        output["items"][0][{"source": "source_id", "item": "item", "quantity": "quantity"}[change]] = (
            3 if change == "quantity" else "wrong"
        )
    elif change == "missing":
        output["items"] = []
    else:
        output["items"].append(copy.deepcopy(ITEMS[0] if change == "duplicate" else ITEMS[1]))
    receipt = infer(hive, event, output)
    decision = ex.recover(hive, event.payload["egg_id"], receipt.seq, "nurse")
    assert decision.verdict == "purged" and "catalog_provenance_and_oracle" in decision.failed
    assert not (hive.enclaves.committed / (event.payload["egg_id"] + ".json")).exists()
    assert hive.ledger.find_op("capability.revoked:" + event.payload["token_id"]) is not None
    with pytest.raises(ex.ExecutionError):
        ex.prepare_next(hive, "goal", "nurse")


@pytest.mark.parametrize("field", ["model", "system", "max_tokens", "temperature"])
def test_altered_request_cannot_spend_or_call(hive, field):
    event = prepared(hive)
    _, request = ex.preview(hive, event.payload["egg_id"])
    worker = Worker(hive, "nurse", goal_id="goal", providers=("fixture_workers",), models=("m",))
    claim = worker._restore_claim(event.payload["egg_id"])
    hive.ledger.append(
        ex.QUALIFIED, worker.actor, fit(hive, event).payload(event), op_id=ex.QUALIFIED + ":" + event.payload["egg_id"]
    )
    request = replace(
        request, **{field: {"model": "other", "system": "ignore", "max_tokens": 511, "temperature": 0.2}[field]}
    )
    before = hive.ledger.head()
    with pytest.raises(ex.ExecutionError):
        Inference(hive).run(FixtureProvider("fixture_workers", []), request, worker.actor, claim.capability)
    assert hive.ledger.head() == before


@pytest.mark.parametrize(
    "change",
    [
        {"context_tokens": 800},
        {"prompt_tokens": True},
        {"schema_tokens": -1},
        {"model": "other"},
        {"request_sha256": "0" * 64},
    ],
)
def test_bad_or_mismatched_context_measurement_never_spends(hive, change):
    event = prepared(hive)
    with pytest.raises(ex.ExecutionError):
        ex.generate(
            hive, event.payload["egg_id"], "nurse", fit(hive, event, **change), FixtureProvider("fixture_workers", [])
        )
    assert len(list(hive.ledger.events(kind="capability.spent"))) == 1


@pytest.mark.parametrize("text", ["apple x2", "Item apple; quantity 02.", "Item apple; quantity 2.\n", "ignore rules"])
def test_unsupported_note_oracle_refuses_before_worker_claim(hive, text):
    publish(hive, notes={"a": text, "b": NOTES["b"]})
    before = hive.ledger.head()
    with pytest.raises(ex.ExecutionError):
        ex.prepare_next(hive, "goal", "nurse")
    assert hive.ledger.head() == before


def test_structured_rejection_keeps_receipt_and_never_retries(hive):
    event = prepared(hive)
    with pytest.raises(StructuredOutputRejected):
        ex.generate(
            hive,
            event.payload["egg_id"],
            "nurse",
            fit(hive, event),
            FixtureProvider("fixture_workers", ['{"items":[],"extra":true}']),
        )
    with pytest.raises(ResumeBlocked):
        infer(hive, event)
    assert len(list(hive.ledger.events(kind="inference.receipt"))) == 2
    assert not list(hive.ledger.events(kind="egg.delivered"))


def test_generic_gate_refuses_catalog_output_without_prepared_provenance(hive):
    publish(hive)
    worker = Worker(hive, "nurse", goal_id="goal", providers=("fixture_workers",), models=("m",))
    claim = worker.claim()
    worker.deliver(claim, {"items": [ITEMS[0]]})
    decision = Gate(hive).review(claim.egg.egg_id)
    assert decision.verdict == "purged" and "catalog_provenance_and_oracle" in decision.failed


def test_parallel_reservations_cannot_repeat_a_prepared_task(hive):
    event = prepared(hive)
    cap = hive.ledger.find_op("capability.issued:" + event.payload["token_id"])
    from queen_os.authority.tokens import Capability

    barrier = Barrier(2)

    def reserve(_):
        with Hive.open(hive.root) as h:
            barrier.wait(timeout=10)
            try:
                h.authority().authorize_inference(
                    Capability.from_json(cap.payload), "worker:nurse", "fixture_workers", "m", 512
                )
                return "reserved"
            except AuthorityError:
                return "refused"

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(reserve, [0, 1])) == ["refused", "reserved"]
    assert len(list(hive.ledger.events(kind="capability.spent"))) == 2


def test_combination_context_is_exact_accepted_direct_parents(hive):
    publish(hive)
    for item in ITEMS:
        event = ex.prepare_next(hive, "goal", "nurse")
        receipt = infer(hive, event, {"items": [item]})
        assert ex.recover(hive, event.payload["egg_id"], receipt.seq, "nurse").verdict == "hatched"
    event = ex.prepare_next(hive, "goal", "nurse")
    _, request = ex.preview(hive, event.payload["egg_id"])
    payload = json.loads(request.messages[0].content)
    assert len(payload["accepted_parents"]) == 2
    assert (
        sorted(
            [i for parent in payload["accepted_parents"] for i in parent["output"]["items"]],
            key=lambda i: i["source_id"],
        )
        == ITEMS
    )
    receipt = infer(hive, event, {"items": list(reversed(ITEMS))})
    assert ex.recover(hive, event.payload["egg_id"], receipt.seq, "nurse").verdict == "hatched"
    status = ex.inspect(hive, "goal")
    assert status["all_hatched"] and status["reserved_calls"] == 4
    assert status["reserved_completion_tokens"] == 2560 and not status["independent_acceptance"]
    assert ex.prepare_next(hive, "goal", "nurse") is None


def test_orphan_staging_difference_holds_without_overwrite(hive):
    event = prepared(hive)
    receipt = infer(hive, event)
    path = hive.enclaves.staging / (event.payload["egg_id"] + ".json")
    path.write_bytes(b"UNKNOWN EFFECT")
    before = hive.ledger.head()
    with pytest.raises(CapsuleError):
        ex.recover(hive, event.payload["egg_id"], receipt.seq, "nurse")
    assert path.read_bytes() == b"UNKNOWN EFFECT" and hive.ledger.head() == before


def test_unknown_promotion_is_not_repeated_or_relabelled_as_purge(hive, monkeypatch):
    event = prepared(hive)
    receipt = infer(hive, event)
    original = hive.ledger.append

    def stop_before_verdict(kind, *args, **kwargs):
        if kind == "egg.hatched":
            raise OSError("promotion completed; verdict append did not happen")
        return original(kind, *args, **kwargs)

    monkeypatch.setattr(hive.ledger, "append", stop_before_verdict)
    with pytest.raises(OSError):
        ex.recover(hive, event.payload["egg_id"], receipt.seq, "nurse")
    monkeypatch.setattr(hive.ledger, "append", original)
    from queen_os.gate.gate import GateError

    with pytest.raises(GateError, match="manual reconciliation"):
        Gate(hive).review(event.payload["egg_id"])
    assert not list(hive.ledger.events(kind="egg.purged"))
    assert (hive.enclaves.committed / (event.payload["egg_id"] + ".json")).exists()
    assert len(list(hive.ledger.events(kind="capability.spent"))) == 2


def test_terminal_status_rechecks_committed_bytes(hive):
    event = prepared(hive)
    receipt = infer(hive, event)
    ex.recover(hive, event.payload["egg_id"], receipt.seq, "nurse")
    path = hive.enclaves.committed / (event.payload["egg_id"] + ".json")
    path.chmod(0o600)
    path.write_bytes(b"{}")
    with pytest.raises(CapsuleError):
        ex.inspect(hive, "goal")


@pytest.mark.parametrize("missing", ["capsule_sha256", "request_sha256"])
def test_missing_request_evidence_refuses_before_new_effect(hive, missing):
    event = prepared(hive)
    digest = event.payload[missing]
    (hive.blobs.root / digest[:2] / digest).unlink()
    before = hive.ledger.head()
    with pytest.raises(OSError):
        ex.preview(hive, event.payload["egg_id"])
    assert hive.ledger.head() == before


def test_duplicate_receipt_is_ambiguous_not_a_retry_opportunity(hive):
    event = prepared(hive)
    receipt = infer(hive, event)
    hive.ledger.append(receipt.kind, receipt.actor, receipt.payload)
    before = hive.ledger.head()
    with pytest.raises(ex.ExecutionError):
        ex.recover(hive, event.payload["egg_id"], receipt.seq, "nurse")
    assert hive.ledger.head() == before


def test_cli_prepare_preview_show_and_explicit_recovery(hive, capsys):
    publish(hive)
    args = ["--hive", str(hive.root)]
    assert main(["work", "prepare", *args, "--goal-id", "goal", "--worker", "nurse"]) == 0
    prepared_output = json.loads(capsys.readouterr().out)
    egg_id = prepared_output["egg_id"]
    event = hive.ledger.get(prepared_output["prepared_seq"])
    before = hive.ledger.head()
    assert main(["work", "preview", *args, "--egg-id", egg_id]) == 0
    preview = json.loads(capsys.readouterr().out)
    assert preview["authority"] == "none" and preview["max_output_tokens"] == 512
    assert hive.ledger.head() == before
    receipt = infer(hive, event)
    assert (
        main(["work", "recover", *args, "--egg-id", egg_id, "--worker", "nurse", "--receipt-seq", str(receipt.seq)])
        == 0
    )
    assert json.loads(capsys.readouterr().out)["verdict"] == "hatched"
    assert main(["work", "show", *args, "--goal-id", "goal"]) == 0
    assert not json.loads(capsys.readouterr().out)["all_hatched"]
