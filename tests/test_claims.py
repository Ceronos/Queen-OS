"""Page-Robinson claiming, per-egg capabilities, fenced delivery: each rule with an adversarial arm."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from queen_os.authority import AuthorityError
from queen_os.comb import StaleFence
from queen_os.comb.projection import fold_eggs, ready
from queen_os.hive import Hive
from queen_os.providers import FixtureProvider, InferenceRequest, Message
from queen_os.providers.receipt import Inference, verify_receipt
from queen_os.queen.egg import lay
from queen_os.workers.claim import OutputRejected, Worker, response

STRICT = {
    "type": "object",
    "properties": {"answer": {"type": "string"}},
    "required": ["answer"],
    "additionalProperties": False,
}


@pytest.fixture
def hive(tmp_path: Path):  # type: ignore[no-untyped-def]
    with Hive.init(tmp_path / "h", "w", mode="test") as h:
        yield h


def test_response_function_is_page_robinson() -> None:
    assert response(0.5, 0.5) == 0.5 and response(1.0, 0.5) == pytest.approx(0.8) and response(0, 0.5) == 0.0


def test_exactly_one_worker_wins_an_egg(hive: Hive) -> None:
    lay(hive, "g", "diploid", {"q": "x"}, STRICT, stimulus=0.9)
    a, b = Worker(hive, "a"), Worker(hive, "b")
    claim = a.claim()
    assert claim is not None and b.claim() is None


def test_capability_is_bound_to_one_worker_and_one_egg(hive: Hive) -> None:
    """QOS-0020: the claim's token names exactly this worker and egg, and expires with the lease."""
    lay(hive, "g", "diploid", {"q": "x"}, STRICT, stimulus=0.9)
    claim = Worker(hive, "a").claim(ttl_ms=5_000)
    assert claim is not None
    cap = claim.capability
    assert cap.subject == "worker:a" and cap.scope == f"egg:{claim.egg.egg_id}"
    assert cap.expires_ms <= claim.lease.expires_ms and cap.grant.max_calls == claim.profile.max_calls
    with pytest.raises(AuthorityError, match="subject"):
        hive.authority().authorize_inference(cap, "worker:b", "scripted", "m", 8)


def test_threshold_filters_low_stimulus_and_orders_by_response(hive: Hive) -> None:
    low = lay(hive, "g", "haploid", {"q": 1}, {}, stimulus=0.2)
    mid = lay(hive, "g", "haploid", {"q": 2}, {}, stimulus=0.6)
    high = lay(hive, "g", "haploid", {"q": 3}, {}, stimulus=0.95)
    picky = Worker(hive, "picky", threshold=0.7)
    assert [e.egg_id for e in picky.candidates()] == [high.egg_id]
    eager = Worker(hive, "eager", threshold=0.1)
    assert [e.egg_id for e in eager.candidates()] == [high.egg_id, mid.egg_id, low.egg_id]


def test_dag_child_waits_for_hatched_parent(hive: Hive) -> None:
    parent = lay(hive, "g", "haploid", {"step": 1}, {}, stimulus=0.9)
    child = lay(hive, "g", "haploid", {"step": 2}, {}, parents=(parent.egg_id,), stimulus=0.9)
    assert [e.egg_id for e in ready(fold_eggs(hive.ledger))] == [parent.egg_id]
    w = Worker(hive, "a")
    claim = w.claim()
    assert claim is not None and claim.egg.egg_id == parent.egg_id
    w.deliver(claim, {"done": True})
    assert child.egg_id not in [e.egg_id for e in ready(fold_eggs(hive.ledger))]  # delivered ≠ hatched
    hive.ledger.append("egg.hatched", "gate", {"egg_id": parent.egg_id}, op_id=f"egg.hatched:{parent.egg_id}")
    assert [e.egg_id for e in ready(fold_eggs(hive.ledger))] == [child.egg_id]


def test_invalid_output_is_rejected_before_anything_is_staged(hive: Hive) -> None:
    lay(hive, "g", "diploid", {"q": "x"}, STRICT, stimulus=0.9)
    w = Worker(hive, "a")
    claim = w.claim()
    assert claim is not None
    for bad in ({}, {"answer": 7}, {"answer": "ok", "extra": "smuggled"}):
        with pytest.raises(OutputRejected):
            w.deliver(claim, bad)
    assert not any((hive.root / "staging").iterdir())
    sha = w.deliver(claim, {"answer": "bee"})
    staged = json.loads((hive.root / "staging" / f"{claim.egg.egg_id}.json").read_bytes())
    assert staged == {"egg_id": claim.egg.egg_id, "output": {"answer": "bee"}} and len(sha) == 64
    assert fold_eggs(hive.ledger)[claim.egg.egg_id].state == "delivered"


def test_lapsed_worker_cannot_deliver_and_successor_takes_over(hive: Hive, monkeypatch: pytest.MonkeyPatch) -> None:
    # A 50 ms wall-clock lease can expire during signing/SQLite on a busy runner.
    # Control only the lease/capability clock; advance it explicitly after a valid claim.
    now = [hive.ledger.now()]
    monkeypatch.setattr(hive.ledger, "now", lambda: now[0])
    lay(hive, "g", "diploid", {"q": "x"}, STRICT, stimulus=0.9)
    slow, fast = Worker(hive, "slow"), Worker(hive, "fast")
    stale = slow.claim(ttl_ms=50)
    assert stale is not None
    now[0] = stale.lease.expires_ms + 1
    fresh = fast.claim(ttl_ms=5_000)
    assert fresh is not None and fresh.lease.token == stale.lease.token + 1
    with pytest.raises(StaleFence):  # Two-arm: the zombie must not stage or deliver
        slow.deliver(stale, {"answer": "late"})
    assert not any((hive.root / "staging").iterdir())
    fast.deliver(fresh, {"answer": "on time"})
    with pytest.raises(AuthorityError):  # and its capability has expired with its lease
        hive.authority().authorize_inference(stale.capability, "worker:slow", "x", "y", 1)


def test_valve_refusal_purges_the_egg_once(hive: Hive) -> None:
    egg = lay(hive, "g", "haploid", {"q": 1}, {}, tools=("shell",), stimulus=0.9)
    assert Worker(hive, "a").claim() is None
    assert fold_eggs(hive.ledger)[egg.egg_id].state == "purged"
    assert Worker(hive, "b").claim() is None
    assert len(list(hive.ledger.events(kind="egg.purged"))) == 1


def test_end_to_end_claim_infer_deliver_with_witnessed_receipt(hive: Hive) -> None:
    lay(hive, "goal-1", "diploid", {"question": "insect that builds a comb"}, STRICT, stimulus=0.9)
    worker = Worker(hive, "a", providers=("scripted",), models=("fixture-model",))
    claim = worker.claim()
    assert claim is not None
    request = InferenceRequest(
        "fixture-model",
        (Message("user", json.dumps(claim.egg.input)),),
        max_tokens=claim.profile.max_output_tokens,
        temperature=claim.profile.temperature,
    )
    provider = FixtureProvider("scripted", ['{"answer": "bee"}', '{"answer": "again"}'])
    witnessed = Inference(hive).run(provider, request, actor=worker.actor, capability=claim.capability)
    with pytest.raises(AuthorityError, match="budget"):  # diploid profile = exactly one call
        Inference(hive).run(provider, request, actor=worker.actor, capability=claim.capability)
    verify_receipt(hive, witnessed.receipt)
    worker.deliver(claim, json.loads(witnessed.result.text))
    kinds = [e.kind for e in hive.ledger.events()]
    assert kinds[-6:] == [
        "capability.issued",
        "egg.claimed",
        "capability.spent",
        "inference.receipt",
        "egg.delivered",
        "lease.released",
    ]
    assert hive.ledger.verify_chain(require_signatures=True) == len(kinds)
