"""VerificationGate: every check has an attack that must end in oophagy (or HOLD), never a promotion."""

from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any

import pytest

from queen_os.authority import AuthorityError
from queen_os.comb.enclaves import EnclaveViolation
from queen_os.comb.projection import fold_eggs, ready
from queen_os.gate.gate import Gate, GateError
from queen_os.hive import Hive
from queen_os.providers import FixtureProvider, InferenceRequest, Message
from queen_os.providers.receipt import Inference
from queen_os.queen.egg import TaskEgg, lay
from queen_os.serial import canonicalize
from queen_os.workers.claim import Claim, Worker

STRICT = {
    "type": "object",
    "properties": {"answer": {"type": "string"}},
    "required": ["answer"],
    "additionalProperties": False,
}


@pytest.fixture
def hive(tmp_path: Path):  # type: ignore[no-untyped-def]
    with Hive.init(tmp_path / "h", "g", mode="test") as h:
        yield h


def run_worker(hive: Hive, model_text: str, *, deliver: dict[str, Any] | None = None, infer: bool = True) -> Claim:
    worker = Worker(hive, "a", providers=("scripted",), models=("m",))
    claim = worker.claim()
    assert claim is not None
    if infer:
        req = InferenceRequest(
            "m", (Message("user", json.dumps(claim.egg.input)),), max_tokens=claim.profile.max_output_tokens
        )
        Inference(hive).run(
            FixtureProvider("scripted", [model_text]), req, actor=worker.actor, capability=claim.capability
        )
    worker.deliver(claim, deliver if deliver is not None else json.loads(model_text))
    return claim


def lay_strict(hive: Hive, **kw: Any) -> TaskEgg:
    return lay(hive, "g", "diploid", {"q": "insect that builds a comb"}, STRICT, stimulus=0.9, **kw)


def test_honest_work_is_promoted_and_unblocks_children(hive: Hive) -> None:
    parent = lay_strict(hive)
    child = lay(hive, "g", "haploid", {"q": "next"}, {}, parents=(parent.egg_id,), stimulus=0.9)
    run_worker(hive, '{"answer": "bee"}')
    d = Gate(hive).review(parent.egg_id)
    assert d.verdict == "hatched" and d.failed == ()
    committed = hive.root / "committed" / f"{parent.egg_id}.json"
    assert json.loads(committed.read_bytes())["output"] == {"answer": "bee"}
    assert not (hive.root / "staging" / f"{parent.egg_id}.json").exists()
    evidence = json.loads(hive.blobs.get(d.evidence_sha))
    assert {c["check"] for c in evidence["checks"]} >= {
        "artifact_present",
        "artifact_digest",
        "artifact_envelope",
        "egg_signature",
        "output_schema",
        "witnessed_inference",
        "output_matches_receipt",
        "promotion",
    }
    assert all(c["ok"] for c in evidence["checks"])
    assert [e.egg_id for e in ready(fold_eggs(hive.ledger))] == [child.egg_id]
    assert Gate(hive).review(parent.egg_id) == d  # idempotent re-review
    assert hive.ledger.verify_chain(require_signatures=True) > 0


def _assert_purged(hive: Hive, egg_id: str, claim: Claim, failed_check: str) -> None:
    d = Gate(hive).review(egg_id)
    assert d.verdict == "purged" and failed_check in d.failed, d
    assert not (hive.root / "committed" / f"{egg_id}.json").exists()
    assert fold_eggs(hive.ledger)[egg_id].state == "purged"
    with pytest.raises(AuthorityError, match="revoked"):  # oophagy revokes the worker's capability
        hive.authority().authorize_inference(claim.capability, "worker:a", "scripted", "m", 1)


def test_artifact_tampered_after_delivery_is_purged(hive: Hive) -> None:
    egg = lay_strict(hive)
    claim = run_worker(hive, '{"answer": "bee"}')
    staged = hive.root / "staging" / f"{egg.egg_id}.json"
    staged.write_bytes(canonicalize({"egg_id": egg.egg_id, "output": {"answer": "wasp"}}))
    _assert_purged(hive, egg.egg_id, claim, "artifact_digest")
    assert (hive.root / "quarantine" / f"{egg.egg_id}.json.quarantine").exists()


def test_invented_output_with_real_receipt_is_purged(hive: Hive) -> None:
    """The model said 'mosquito'. The worker delivered 'bee'. The receipt is real but doesn't back the output."""
    egg = lay_strict(hive)
    claim = run_worker(hive, '{"answer": "mosquito"}', deliver={"answer": "bee"})
    _assert_purged(hive, egg.egg_id, claim, "output_matches_receipt")


def test_unwitnessed_output_is_purged(hive: Hive) -> None:
    egg = lay_strict(hive)
    claim = run_worker(hive, "", deliver={"answer": "bee"}, infer=False)
    _assert_purged(hive, egg.egg_id, claim, "witnessed_inference")


def test_schema_bypass_written_straight_to_staging_is_purged(hive: Hive) -> None:
    """A worker that skips deliver()'s validation and writes staging + ledger itself."""
    egg = lay_strict(hive)
    worker = Worker(hive, "a", providers=("scripted",), models=("m",))
    claim = worker.claim()
    assert claim is not None
    req = InferenceRequest("m", (Message("user", "x"),), max_tokens=64)
    Inference(hive).run(
        FixtureProvider("scripted", ['{"answer": 42}']), req, actor=worker.actor, capability=claim.capability
    )
    body = canonicalize({"egg_id": egg.egg_id, "output": {"answer": 42}})
    sha = hive.enclaves.stage(f"{egg.egg_id}.json", body)
    hive.ledger.append(
        "egg.delivered",
        worker.actor,
        {
            "artifact_sha": sha,
            "egg_id": egg.egg_id,
            "lease_token": claim.lease.token,
            "token_id": claim.capability.token_id,
        },
        fence=claim.lease.fence,
        op_id=f"egg.delivered:{egg.egg_id}",
    )
    _assert_purged(hive, egg.egg_id, claim, "output_schema")


def test_fixture_receipt_is_purged_once_the_hive_is_production(hive: Hive) -> None:
    egg = lay_strict(hive)
    claim = run_worker(hive, '{"answer": "bee"}')
    root = hive.root
    hive.close()
    manifest = root / "hive.json"
    manifest.chmod(0o644)
    manifest.write_text(manifest.read_text().replace('"mode":"test"', '"mode":"production"'))
    with Hive.open(root) as prod:
        _assert_purged(prod, egg.egg_id, claim, "witnessed_inference")


def test_quorum_eggs_are_held_not_promoted(hive: Hive) -> None:
    egg = lay(hive, "g", "diploid", {"q": "x"}, STRICT, tools=("shell",), stimulus=0.9)
    run_worker(hive, '{"answer": "ok"}')
    d = Gate(hive).review(egg.egg_id)
    assert d.verdict == "held" and d.failed == ("quorum",)
    assert fold_eggs(hive.ledger)[egg.egg_id].state == "delivered"
    assert (hive.root / "staging" / f"{egg.egg_id}.json").exists()
    assert not (hive.root / "committed" / f"{egg.egg_id}.json").exists()


def test_two_gates_cannot_decide_the_same_egg(hive: Hive) -> None:
    egg = lay_strict(hive)
    run_worker(hive, '{"answer": "bee"}')
    hive.leases.acquire(f"gate:{egg.egg_id}", "gate:other", 10_000)
    with pytest.raises(GateError, match="another gate"):
        Gate(hive).review(egg.egg_id)


def test_undelivered_eggs_are_not_reviewable(hive: Hive) -> None:
    egg = lay_strict(hive)
    with pytest.raises(GateError, match="not delivered"):
        Gate(hive).review(egg.egg_id)


def test_qos_0009_concurrent_promotion_has_exactly_one_winner(hive: Hive) -> None:
    sha = hive.enclaves.stage("race.json", b'{"x":1}')
    results: list[str] = []
    barrier = threading.Barrier(2)

    def promote() -> None:
        barrier.wait()
        try:
            hive.enclaves.promote("race.json", sha)
            results.append("won")
        except (EnclaveViolation, FileNotFoundError):
            results.append("lost")

    threads = [threading.Thread(target=promote) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert sorted(results) == ["lost", "won"]
    assert (hive.root / "committed" / "race.json").read_bytes() == b'{"x":1}'
    assert not list((hive.root / "committed").glob(".promote-*"))


def test_qos_0009_existing_commit_is_never_overwritten(hive: Hive) -> None:
    sha1 = hive.enclaves.stage("a.json", b"first")
    hive.enclaves.promote("a.json", sha1)
    sha2 = hive.enclaves.stage("a.json", b"second")
    with pytest.raises(EnclaveViolation):
        hive.enclaves.promote("a.json", sha2)
    assert (hive.root / "committed" / "a.json").read_bytes() == b"first"


def test_cli_eggs_and_gate_review(hive: Hive, capsys: pytest.CaptureFixture[str]) -> None:
    from queen_os.cli import main

    egg = lay_strict(hive)
    run_worker(hive, '{"answer": "bee"}')
    root = str(hive.root)
    assert main(["eggs", "--hive", root]) == 0
    assert "delivered" in capsys.readouterr().out
    assert main(["gate", "review", egg.egg_id, "--hive", root]) == 0
    assert '"verdict": "hatched"' in capsys.readouterr().out
