"""Offline planner/budget/recovery contracts. Every model double is fixture-classified."""

from __future__ import annotations

import copy
import json
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest

from queen_os.authority import Grant
from queen_os.authority.tokens import AuthorityError
from queen_os.cli import main
from queen_os.gate.gate import Gate
from queen_os.hive import Hive
from queen_os.providers import FixtureProvider, InferenceRequest, JsonSchemaOutput, Message
from queen_os.providers.receipt import Inference, verify_receipt
from queen_os.queen import planner
from queen_os.queen.oviposition import PlanBudget, publish_plan, read_plan
from queen_os.queen.run_budget import SOURCE, RunBudget, RunBudgetError
from queen_os.serial.afser import DigestDivergence
from queen_os.serial.jcs import canonicalize
from queen_os.workers.claim import Worker

OBJECTIVE = "Extract item names and quantities from each note and combine them, preserving source IDs."
NOTES = {"note_a": "Item apple; quantity 2.", "note_b": "Item pear; quantity 3."}
PROPOSAL = {
    "v": 1,
    "tasks": [
        {"id": "combine", "kind": "combine_items", "source_id": "", "parents": ["extract_b", "extract_a"]},
        {"id": "extract_a", "kind": "extract_items", "source_id": "note_a", "parents": []},
        {"id": "extract_b", "kind": "extract_items", "source_id": "note_b", "parents": []},
    ],
}


@pytest.fixture
def hive(tmp_path):
    with Hive.init(tmp_path / "hive", "planner", mode="test") as value:
        yield value


def setup(hive, proposal=None, budget=None, goal="test_goal"):
    provider = FixtureProvider("local_plan_fixture", [json.dumps(PROPOSAL if proposal is None else proposal)])
    planner.prepare(hive, goal, OBJECTIVE, NOTES, budget or RunBudget(), provider, "m")
    return provider


def accepted(hive):
    provider = setup(hive)
    source = planner.generate(hive, "test_goal", provider)
    return provider, source


def token(hive, scope="planner:test_goal", subject=planner.ACTOR, **kwargs):
    grant = Grant(providers=("local_plan_fixture",), models=("m",), max_calls=10, max_output_tokens=2048, **kwargs)
    return hive.authority().issue(subject, scope, grant, 60_000)


def test_witness_compile_publish_and_reopen_preserve_provenance(hive):
    _, source = accepted(hive)
    assert source.payload["provider_kind"] == "fixture"
    receipt = hive.ledger.get(source.payload["receipt_seq"])
    assert json.loads(verify_receipt(hive, receipt).text) == PROPOSAL
    compiled = json.loads(hive.blobs.get(source.payload["compiled_sha256"]))
    assert compiled != PROPOSAL  # The host expansion is explicit, not disguised as model output.
    assert all(t["tools"] == [] and t["ploidy"] == "diploid" for t in compiled["tasks"])
    published = planner.publish(hive, "test_goal")
    assert len(published.eggs) == 3 and not published.existing
    state = planner.inspect(hive, "test_goal")
    assert state["status"] == "PUBLISHED" and state["reserved_calls"] == 1
    assert state["reserved_completion_tokens"] == 1024 and state["semantic_goal_acceptance"] == "not_assessed"
    before = hive.ledger.head().seq
    assert planner.publish(hive, "test_goal").existing
    assert hive.ledger.head().seq == before
    with Hive.open(hive.root) as reopened:
        assert read_plan(reopened, "test_goal").proposal_sha256 == published.proposal_sha256
        assert planner.inspect(reopened, "test_goal")["status"] == "PUBLISHED"
        assert reopened.ledger.verify_chain(require_signatures=True) == before


def test_planner_plus_workers_share_fixed_allocations_and_gate_contract(hive):
    accepted(hive)
    planner.publish(hive, "test_goal")
    worker = Worker(hive, "fixture_worker", providers=("local_plan_fixture",), models=("m",))
    expected = [
        {"source_id": "note_a", "item": "apple", "quantity": 2},
        {"source_id": "note_b", "item": "pear", "quantity": 3},
    ]
    for _ in range(3):
        claim = worker.claim()
        assert claim is not None
        if "source" in claim.egg.input:
            items = [i for i in expected if i["source_id"] == claim.egg.input["source"]["id"]]
        else:
            items = expected
        result = {"items": items}
        provider = FixtureProvider("local_plan_fixture", [json.dumps(result)])
        request = InferenceRequest(
            "m", (Message("user", "synthetic task"),), max_tokens=512, output=JsonSchemaOutput(claim.egg.schema)
        )
        witnessed = Inference(hive).run(provider, request, worker.actor, claim.capability)
        worker.deliver(claim, json.loads(witnessed.result.text))
        assert Gate(hive).review(claim.egg.egg_id).verdict == "hatched"
    assert worker.claim() is None
    state = planner.inspect(hive, "test_goal")
    assert (state["reserved_calls"], state["reserved_completion_tokens"]) == (4, 2560)
    spends = list(hive.ledger.events(kind="capability.spent"))
    assert [e.payload["run"]["phase"] for e in spends] == ["planning", "workers", "workers", "workers"]
    assert all(e.payload["provider_kind"] == "fixture" for e in hive.ledger.events(kind="inference.receipt"))


@pytest.mark.parametrize(
    "change",
    [
        {"max_tasks": True},
        {"max_tasks": 1},
        {"max_tasks": 4},
        {"max_calls": 3},
        {"max_completion_tokens": 2559},
        {"planner_output_tokens": 2049},
        {"planner_output_tokens": 0},
        {"max_completion_tokens": True},
        {"max_calls": 5},
    ],
)
def test_bad_allocations_refuse_before_record_or_network(hive, change):
    with pytest.raises(RunBudgetError):
        setup(hive, budget=RunBudget(**change))
    assert [e.kind for e in hive.ledger.events()] == ["hive.genesis"]


@pytest.mark.parametrize(
    "mutation",
    [
        "extra_field",
        "unknown_kind",
        "missing_source",
        "duplicate_source",
        "duplicate_id",
        "cycle",
        "missing_parent",
        "duplicate_parent",
        "too_many",
        "wrong_version",
        "nonempty_merge_source",
        "extra_extract_parent",
    ],
)
def test_bad_model_graphs_keep_spend_and_receipt_but_publish_nothing(hive, mutation):
    value = copy.deepcopy(PROPOSAL)
    if mutation == "extra_field":
        value["tasks"][1]["tools"] = ["shell"]
    if mutation == "unknown_kind":
        value["tasks"][1]["kind"] = "run_code"
    if mutation == "missing_source":
        value["tasks"][1]["source_id"] = "outside"
    if mutation == "duplicate_source":
        value["tasks"][2]["source_id"] = "note_a"
    if mutation == "duplicate_id":
        value["tasks"][2]["id"] = "extract_a"
    if mutation == "cycle":
        value["tasks"][0]["parents"] = ["combine"]
    if mutation == "missing_parent":
        value["tasks"][0]["parents"] = ["extract_a"]
    if mutation == "duplicate_parent":
        value["tasks"][0]["parents"] *= 2
    if mutation == "too_many":
        value["tasks"].append(copy.deepcopy(value["tasks"][1]))
    if mutation == "wrong_version":
        value["v"] = 2
    if mutation == "nonempty_merge_source":
        value["tasks"][0]["source_id"] = "note_a"
    if mutation == "extra_extract_parent":
        value["tasks"][1]["parents"] = ["extract_b"]
    provider = setup(hive, value)
    with pytest.raises((ValueError, PermissionError)):
        planner.generate(hive, "test_goal", provider)
    assert len(list(hive.ledger.events(kind="capability.spent"))) == 1
    assert len(list(hive.ledger.events(kind="inference.receipt"))) == 1
    assert not list(hive.ledger.events(kind="egg.laid")) and not list(hive.ledger.events(kind=SOURCE))
    with pytest.raises(planner.PlannerError, match="already reserved"):
        planner.generate(hive, "test_goal", provider)


def test_transport_uncertainty_consumes_planner_allowance_across_replacement_caps(hive, monkeypatch):
    provider = setup(hive)

    def lost(*_):
        raise OSError("synthetic transport outcome unknown")

    monkeypatch.setattr(provider, "send", lost)
    with pytest.raises(OSError):
        planner.generate(hive, "test_goal", provider)
    assert planner.inspect(hive, "test_goal")["status"] == "UNKNOWN_AFTER_SPEND"
    with pytest.raises(planner.PlannerError):
        planner.generate(hive, "test_goal", provider)
    cap = token(hive)
    with pytest.raises(AuthorityError):
        hive.authority().authorize_inference(cap, planner.ACTOR, "local_plan_fixture", "m", 128)
    assert len(list(hive.ledger.events(kind="capability.spent"))) == 1


def test_short_actual_output_does_not_refund_requested_allowance(hive):
    accepted(hive)
    assert planner.inspect(hive, "test_goal")["reserved_completion_tokens"] == 1024
    with pytest.raises(AuthorityError):
        hive.authority().authorize_inference(token(hive), planner.ACTOR, "local_plan_fixture", "m", 1)


def test_run_disallows_tools_and_other_routes_even_with_broad_cap(hive):
    setup(hive)
    cap = hive.authority().issue(
        planner.ACTOR,
        "planner:test_goal",
        Grant(tools=("read_note",), providers=("*",), models=("*",), max_calls=10, max_output_tokens=2048),
        60_000,
    )
    with pytest.raises(AuthorityError):
        hive.authority().authorize_tool(cap, planner.ACTOR, "read_note")
    with pytest.raises(AuthorityError):
        hive.authority().authorize_inference(cap, planner.ACTOR, "elsewhere", "m", 1024)
    with pytest.raises(AuthorityError):
        hive.authority().authorize_inference(cap, planner.ACTOR, "local_plan_fixture", "different", 1024)
    with pytest.raises(AuthorityError):
        hive.authority().authorize_inference(cap, planner.ACTOR, "local_plan_fixture", "m", 1025)
    assert not list(hive.ledger.events(kind="capability.spent"))


def test_missing_prepared_run_refuses_new_planner_scope(hive):
    with pytest.raises(AuthorityError):
        hive.authority().authorize_inference(token(hive), planner.ACTOR, "local_plan_fixture", "m", 1024)


def test_concurrent_replacement_caps_cannot_overspend_planner_pool(hive):
    setup(hive)
    barrier = Barrier(2)

    def reserve(_):
        with Hive.open(hive.root) as h:
            cap = token(h)
            barrier.wait(timeout=10)
            try:
                h.authority().authorize_inference(cap, planner.ACTOR, "local_plan_fixture", "m", 1024)
                return "reserved"
            except AuthorityError:
                return "refused"

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(reserve, [0, 1])) == ["refused", "reserved"]
    assert len(list(hive.ledger.events(kind="capability.spent"))) == 1


@pytest.mark.parametrize(
    "bad",
    [
        None,
        {"goal_id": "test_goal"},
        {"goal_id": "test_goal", "run_hash": "0" * 64, "phase": "planning", "completion_tokens": 1024},
    ],
)
def test_missing_or_inconsistent_prior_run_charges_refuse(hive, bad):
    setup(hive)
    cap = token(hive)
    payload = {
        "token_id": cap.token_id,
        "n": 1,
        "action": {"type": "inference", "provider": "local_plan_fixture", "model": "m"},
    }
    if bad is not None:
        payload["run"] = bad
    hive.ledger.append("capability.spent", planner.ACTOR, payload)
    with pytest.raises(AuthorityError):
        hive.authority().authorize_inference(token(hive), planner.ACTOR, "local_plan_fixture", "m", 128)


def test_lost_receipt_return_recovers_without_second_request(hive, monkeypatch):
    provider = setup(hive)
    original = hive.ledger._post_write_fetch

    def fail(seq):
        event = original(seq)
        if event.kind == "inference.receipt":
            raise OSError("committed receipt return lost")
        return event

    monkeypatch.setattr(hive.ledger, "_post_write_fetch", fail)
    with pytest.raises(OSError):
        planner.generate(hive, "test_goal", provider)
    monkeypatch.setattr(hive.ledger, "_post_write_fetch", original)
    receipt = list(hive.ledger.events(kind="inference.receipt"))[0]
    planner.accept_receipt(hive, "test_goal", receipt.seq)
    before = hive.ledger.head().seq
    planner.accept_receipt(hive, "test_goal", receipt.seq)
    assert hive.ledger.head().seq == before
    planner.publish(hive, "test_goal")
    assert len(list(hive.ledger.events(kind="inference.receipt"))) == 1


def test_uncertain_publication_is_read_back_not_duplicated(hive, monkeypatch):
    accepted(hive)
    original = hive.ledger._post_write_fetch

    def fail(seq):
        event = original(seq)
        if event.kind == "goal.planned":
            raise OSError("committed plan return lost")
        return event

    monkeypatch.setattr(hive.ledger, "_post_write_fetch", fail)
    with pytest.raises(OSError):
        planner.publish(hive, "test_goal")
    monkeypatch.setattr(hive.ledger, "_post_write_fetch", original)
    before = hive.ledger.head().seq
    assert read_plan(hive, "test_goal").existing
    assert planner.publish(hive, "test_goal").existing and hive.ledger.head().seq == before
    assert len(list(hive.ledger.events(kind="egg.laid"))) == 3


def test_prepared_goal_cannot_accept_unwitnessed_or_altered_publication(hive):
    provider = setup(hive)
    raw = planner.compile_proposal(json.dumps(PROPOSAL), NOTES, RunBudget())
    with pytest.raises(planner.PlannerError):
        publish_plan(hive, "test_goal", raw, planner.worker_budget(RunBudget()), objective=OBJECTIVE)
    planner.generate(hive, "test_goal", provider)
    changed = json.loads(raw)
    changed["tasks"][0]["input"] = {"invented": "input"}
    for proposal, budget, objective in [
        (canonicalize(changed), planner.worker_budget(RunBudget()), OBJECTIVE),
        (raw, PlanBudget(4, 2048, 3), OBJECTIVE),
        (raw, planner.worker_budget(RunBudget()), "different"),
    ]:
        with pytest.raises(planner.PlannerError):
            publish_plan(hive, "test_goal", proposal, budget, objective=objective)
    assert not list(hive.ledger.events(kind="egg.laid"))


@pytest.mark.parametrize("what", ["response", "compiled"])
def test_source_blob_corruption_stops_publication_and_status(hive, what):
    _, source = accepted(hive)
    sha = (
        source.payload["compiled_sha256"]
        if what == "compiled"
        else hive.ledger.get(source.payload["receipt_seq"]).payload["response_sha"]
    )
    path = hive.blobs._path(sha)
    path.write_bytes(b"corrupted")
    with pytest.raises((ValueError, PermissionError, OSError, DigestDivergence)):
        planner.publish(hive, "test_goal")
    with pytest.raises((ValueError, PermissionError, OSError, DigestDivergence)):
        planner.inspect(hive, "test_goal")


def test_production_fixture_refusal_and_local_route_preflight(tmp_path):
    provider = FixtureProvider("local_plan_fixture", [])
    with Hive.init(tmp_path / "production", "prod") as h:
        with pytest.raises(planner.PlannerError):
            planner.prepare(h, "g", OBJECTIVE, NOTES, RunBudget(), provider, "m")
        assert h.ledger.head().seq == 1
    with pytest.raises(ValueError):
        planner.local_provider("https://remote.example/v1")
    request = planner.request_for("model", OBJECTIVE, NOTES, RunBudget())
    wire = planner.local_provider().encode(request)
    body = json.loads(wire.body)
    assert "tools" not in body and "authorization" not in wire.headers
    assert body["max_tokens"] == 1024 and body["response_format"]["json_schema"]["strict"] is True
    assert len(wire.body) <= planner.MAX_REQUEST_BYTES


def test_cli_preview_has_no_authority_and_requires_separate_context_fit(tmp_path, capsys):
    path = tmp_path / "brief.json"
    path.write_text(json.dumps({"objective": OBJECTIVE, "notes": NOTES}))
    assert main(["goal", "preview", str(path), "--model", "model"]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["native_token_count"] is None and result["authority"] == "none"
    assert result["worker_completion_tokens"] == 1536
    assert main(["goal", "preview", str(path), "--model", "model", "--calls", "3"]) == 2


@pytest.mark.parametrize(
    "value",
    [
        {},
        {"objective": OBJECTIVE, "notes": {}},
        {"objective": "", "notes": NOTES},
        {"objective": OBJECTIVE, "notes": {"n": "x" * 513}},
        {"objective": OBJECTIVE, "notes": {"../path": "data"}},
        {"objective": OBJECTIVE, "notes": {"a": "1", "b": "2", "c": "3"}},
        {"objective": OBJECTIVE, "notes": NOTES, "tools": ["shell"]},
        {"objective": "x" * 1001, "notes": NOTES},
    ],
)
def test_brief_rejects_unbounded_or_unsupported_inputs(value):
    with pytest.raises(ValueError):
        planner.brief(json.dumps(value).encode())


def test_duplicate_and_oversized_brief_bytes_refused():
    for raw in [b'{"objective":"a","objective":"b","notes":{}}', b"x" * 4097, b"\xff"]:
        with pytest.raises(ValueError):
            planner.brief(raw)


def test_prepared_intent_return_loss_is_not_silently_restarted(hive, monkeypatch):
    original = hive.ledger._post_write_fetch

    def fail(seq):
        event = original(seq)
        if event.kind == "goal.run_prepared":
            raise OSError("prepared commit return lost")
        return event

    monkeypatch.setattr(hive.ledger, "_post_write_fetch", fail)
    with pytest.raises(OSError):
        setup(hive)
    monkeypatch.setattr(hive.ledger, "_post_write_fetch", original)
    assert planner.inspect(hive, "test_goal")["status"] == "PREPARED"
    with pytest.raises(planner.PlannerError, match="already recorded"):
        setup(hive)
    assert not list(hive.ledger.events(kind="capability.spent"))


def test_source_return_loss_recovery_is_only_bookkeeping(hive, monkeypatch):
    provider = setup(hive)
    original = hive.ledger._post_write_fetch

    def fail(seq):
        event = original(seq)
        if event.kind == SOURCE:
            raise OSError("source commit return lost")
        return event

    monkeypatch.setattr(hive.ledger, "_post_write_fetch", fail)
    with pytest.raises(OSError):
        planner.generate(hive, "test_goal", provider)
    monkeypatch.setattr(hive.ledger, "_post_write_fetch", original)
    assert planner.inspect(hive, "test_goal")["status"] == "SOURCE_ACCEPTED"
    planner.publish(hive, "test_goal")
    assert len(list(hive.ledger.events(kind="inference.receipt"))) == 1


def test_receipt_from_a_different_run_cannot_be_attached(hive):
    provider = setup(hive)
    source = planner.generate(hive, "test_goal", provider)
    setup(hive, goal="different_goal")
    with pytest.raises(planner.PlannerError):
        planner.accept_receipt(hive, "different_goal", source.payload["receipt_seq"])
    assert not hive.ledger.find_op(SOURCE + ":different_goal")


def test_duplicate_receipt_identity_for_spend_is_ambiguous(hive):
    _, source = accepted(hive)
    receipt = hive.ledger.get(source.payload["receipt_seq"])
    hive.ledger.append(receipt.kind, receipt.actor, receipt.payload)
    with pytest.raises(planner.PlannerError, match="multiple receipts"):
        planner.publish(hive, "test_goal")


def test_one_note_catalog_preserves_a_smaller_graph(hive):
    notes = {"only_note": "Item apple; quantity 2."}
    proposal = {
        "v": 1,
        "tasks": [
            {"id": "extract", "kind": "extract_items", "source_id": "only_note", "parents": []},
            {"id": "combine", "kind": "combine_items", "source_id": "", "parents": ["extract"]},
        ],
    }
    budget = RunBudget(max_calls=3, max_completion_tokens=2048, max_tasks=2)
    provider = FixtureProvider("local_plan_fixture", [json.dumps(proposal)])
    planner.prepare(hive, "small", OBJECTIVE, notes, budget, provider, "m")
    planner.generate(hive, "small", provider)
    assert len(planner.publish(hive, "small").eggs) == 2


def test_changed_template_is_not_published(hive, monkeypatch):
    accepted(hive)
    monkeypatch.setattr(planner, "EXTRACT", "changed template")
    with pytest.raises(planner.PlannerError, match="contract/source mismatch"):
        planner.publish(hive, "test_goal")
