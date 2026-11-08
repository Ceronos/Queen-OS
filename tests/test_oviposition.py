"""Goal planning fixtures: graph admission, atomic publication and shared spend ceilings."""

from __future__ import annotations

import json
import sqlite3
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

import pytest

from queen_os.authority import AuthorityError, Grant
from queen_os.comb.capsule import build_capsule
from queen_os.comb.ledger import ChainBroken, IdempotencyConflict
from queen_os.comb.projection import fold_eggs, ready
from queen_os.gate.gate import Gate
from queen_os.hive import Hive
from queen_os.providers import FixtureProvider, InferenceRequest, Message
from queen_os.providers.receipt import Inference, verify_receipt
from queen_os.queen.egg import lay, load
from queen_os.queen.oviposition import PlanBudget, PlanError, publish_plan, read_plan, validate_proposal
from queen_os.serial.jcs import canonicalize
from queen_os.workers.claim import Worker

SCHEMA = {
    "type": "object",
    "properties": {"answer": {"type": "string"}},
    "required": ["answer"],
    "additionalProperties": False,
}
BUDGET = PlanBudget(32, 32768, 32)


@pytest.fixture
def hive(tmp_path: Path):  # type: ignore[no-untyped-def]
    with Hive.init(tmp_path / "h", "planning", mode="test") as h:
        yield h


def task(ident: str = "a", parents: tuple[str, ...] = (), **changes: Any) -> dict[str, Any]:
    return {
        "id": ident,
        "ploidy": "diploid",
        "input": {"q": "fixture 🐝"},
        "schema": SCHEMA,
        "tools": [],
        "stimulus": 0.9,
        "parents": list(parents),
        **changes,
    }


def raw(*nodes: dict[str, Any]) -> bytes:
    return canonicalize({"v": 1, "tasks": list(nodes) or [task()]})


def publish(hive: Hive, data: bytes | None = None, budget: PlanBudget = BUDGET):  # type: ignore[no-untyped-def]
    return publish_plan(
        hive, "goal_fixture", raw() if data is None else data, budget, objective="Synthetic fixture goal"
    )


def test_validation_is_pure_and_orders_dependencies(hive: Hive) -> None:
    before = hive.ledger.head()
    p = validate_proposal(raw(task("z", ("a",)), task("a")), BUDGET)
    assert p.order == ("a", "z") and p.calls == 2 and p.completion_tokens == 1024
    p.proposal["tasks"].clear()
    assert len(p.proposal["tasks"]) == 2 and hive.ledger.head() == before


@pytest.mark.parametrize(
    "mutation",
    [
        "version_bool",
        "unknown_top",
        "empty",
        "duplicate_id",
        "duplicate_parent",
        "self_cycle",
        "cycle",
        "dangling",
        "unsafe_id",
        "missing_field",
        "grant_field",
        "tool_not_allowed",
        "bool_stimulus",
        "outside_stimulus",
        "input_not_object",
        "input_overflow",
        "open_schema",
        "remote_ref",
    ],
)
def test_bad_proposals_write_nothing(hive: Hive, mutation: str) -> None:
    p: dict[str, Any] = json.loads(raw())
    n = p["tasks"][0]
    if mutation == "version_bool":
        p["v"] = True
    elif mutation == "unknown_top":
        p["budget"] = {"max_calls": 100000}
    elif mutation == "empty":
        p["tasks"] = []
    elif mutation == "duplicate_id":
        p["tasks"].append(task())
    elif mutation == "duplicate_parent":
        p["tasks"] = [task("a"), task("b", ("a", "a"))]
    elif mutation == "self_cycle":
        n["parents"] = ["a"]
    elif mutation == "cycle":
        p["tasks"] = [task("a", ("b",)), task("b", ("a",))]
    elif mutation == "dangling":
        n["parents"] = ["outside"]
    elif mutation == "unsafe_id":
        n["id"] = "../escape"
    elif mutation == "missing_field":
        del n["schema"]
    elif mutation == "grant_field":
        n["signature"] = "pretend-host"
    elif mutation == "tool_not_allowed":
        n["tools"] = ["shell"]
    elif mutation == "bool_stimulus":
        n["stimulus"] = True
    elif mutation == "outside_stimulus":
        n["stimulus"] = 1.1
    elif mutation == "input_not_object":
        n["input"] = "prompt authority"
    elif mutation == "input_overflow":
        n["input"] = {"q": "x" * 8000}
    elif mutation == "open_schema":
        n["schema"] = {**SCHEMA, "additionalProperties": True}
    elif mutation == "remote_ref":
        n["schema"] = {"$ref": "https://not-a-fetch.invalid/schema"}
    before = hive.ledger.head()
    with pytest.raises(PlanError):
        publish(hive, canonicalize(p))
    assert hive.ledger.head() == before and not list(hive.ledger.events(kind="egg.laid"))


@pytest.mark.parametrize(
    "data",
    [
        b'{"v":1,"v":1,"tasks":[]}',
        b'{"v":1,"tasks":[],"x":NaN}',
        b"x" * 32769,
        '{"v":1,"tasks":[]}'.encode("utf-16"),
    ],
)
def test_ambiguous_encoding_and_packet_overflow_refused(hive: Hive, data: bytes) -> None:
    before = hive.ledger.head()
    with pytest.raises(PlanError):
        publish(hive, data)
    assert hive.ledger.head() == before


@pytest.mark.parametrize(
    "budget",
    [
        PlanBudget(True, 512),
        PlanBudget(1, False),
        PlanBudget(0, 512),
        PlanBudget(1, 511),
        PlanBudget(1, 512, 0),
        PlanBudget(1, 512, 33),
        PlanBudget(10001, 512),
        PlanBudget(1, 1048577),
        PlanBudget(1, 512, allowed_tools=["read_data"]),  # type: ignore[arg-type]
    ],
)
def test_invalid_or_insufficient_host_budget_is_not_a_proposal_override(hive: Hive, budget: PlanBudget) -> None:
    before = hive.ledger.head()
    with pytest.raises(PlanError):
        publish(hive, budget=budget)
    assert hive.ledger.head() == before


def test_budget_and_task_count_apply_to_all_derived_profiles(hive: Hive) -> None:
    for budget in [PlanBudget(1, 1024), PlanBudget(2, 1023), PlanBudget(2, 1024, 1)]:
        with pytest.raises(PlanError):
            publish(hive, raw(task("a"), task("b")), budget)
    with pytest.raises(PlanError):
        publish(hive, raw(task(ploidy="haploid")), PlanBudget(2, 3072))
    with pytest.raises(PlanError):
        publish(hive, raw(task(ploidy="haploid")), PlanBudget(3, 3071))
    assert hive.ledger.head().seq == 1  # type: ignore[union-attr]


def test_graph_depth_and_edge_limits(hive: Hive) -> None:
    deep = [task("n" + str(i), ("n" + str(i - 1),) if i else ()) for i in range(10)]
    with pytest.raises(PlanError, match="depth"):
        publish(hive, raw(*deep))
    dense = [task("n" + str(i), tuple("n" + str(j) for j in range(max(0, i - 16), i))) for i in range(18)]
    with pytest.raises(PlanError, match="edge"):
        publish(hive, raw(*dense))


def test_valid_maximum_depth_and_shared_ancestors(hive: Hive) -> None:
    nodes = [task("n" + str(i), ("n" + str(i - 1),) if i else ()) for i in range(9)]
    nodes.append(task("short", ("n0", "n1")))
    result = publish(hive, raw(*reversed(nodes)))
    assert len(result.eggs) == 10 and all(load(hive, e.egg_id) == e for e in result.eggs)


def test_host_tool_allowlist_does_not_bypass_valve(hive: Hive) -> None:
    with pytest.raises(PlanError, match="M2"):
        publish(hive, raw(task(tools=["shell"])), PlanBudget(1, 512, allowed_tools=("shell",)))
    with pytest.raises(PlanError):
        publish(hive, raw(task(tools=["read_data", "read_data"])), PlanBudget(1, 512, allowed_tools=("read_data",)))


def test_atomic_publication_idempotency_and_readback(hive: Hive) -> None:
    data = raw(task("child", ("parent",)), task("parent"))
    result = publish(hive, data)
    before = hive.ledger.head()
    assert result.existing is False and result.eggs[0].parents == ()
    assert result.eggs[1].parents == (result.eggs[0].egg_id,)
    assert publish(hive, b" \n" + data).existing and read_plan(hive, result.goal_id).eggs == result.eggs
    assert hive.ledger.head() == before and hive.ledger.verify_chain(require_signatures=True) == 4
    assert not list(hive.ledger.events(kind="capability.issued"))
    for changed in [raw(task("different")), data]:
        with pytest.raises(IdempotencyConflict):
            publish(hive, changed, PlanBudget(33, 32768))
    with pytest.raises(IdempotencyConflict):
        publish_plan(hive, result.goal_id, data, BUDGET, objective="Changed host objective")


def test_broader_capability_cannot_add_a_tool_to_the_published_task(hive: Hive) -> None:
    e = publish(hive).eggs[0]
    cap = hive.authority().issue("worker:a", "egg:" + e.egg_id, Grant(tools=("write_data",)), 60000)
    before = hive.ledger.head()
    with pytest.raises(AuthorityError, match="plan budget"):
        hive.authority().authorize_tool(cap, "worker:a", "write_data")
    assert hive.ledger.head() == before


@pytest.mark.parametrize("goal,objective", [("../unsafe", "goal"), ("g", ""), ("g", "x" * 8001)])
def test_host_goal_identity_and_objective_are_bounded(hive: Hive, goal: str, objective: str) -> None:
    before = hive.ledger.head()
    with pytest.raises(PlanError):
        publish_plan(hive, goal, raw(), BUDGET, objective=objective)
    assert hive.ledger.head() == before


def test_standalone_goal_history_is_not_retroactively_budgeted(hive: Hive) -> None:
    lay(hive, "goal_fixture", "diploid", {"q": "fixture"}, SCHEMA)
    before = hive.ledger.head()
    with pytest.raises(PlanError, match="standalone"):
        publish(hive)
    assert hive.ledger.head() == before


def test_mid_publication_exception_rolls_back_all_events(hive: Hive, monkeypatch: pytest.MonkeyPatch) -> None:
    original, before = hive.ledger.append_locked, hive.ledger.head()
    count = 0

    def fail_after_insert(*args, **kwargs):  # type: ignore[no-untyped-def]
        nonlocal count
        number = original(*args, **kwargs)
        count += 1
        if count == 2:
            raise RuntimeError("fixture inserted then failed")
        return number

    with monkeypatch.context() as patch:
        patch.setattr(hive.ledger, "append_locked", fail_after_insert)
        with pytest.raises(RuntimeError, match="inserted"):
            publish(hive, raw(task("a"), task("b")))
    assert hive.ledger.head() == before and not list(hive.ledger.events(kind="egg.laid"))
    assert len(publish(hive, raw(task("a"), task("b"))).eggs) == 2


def test_failed_commit_exposes_no_partial_graph(hive: Hive, monkeypatch: pytest.MonkeyPatch) -> None:
    with hive.ledger.transaction() as db:
        db.execute("CREATE TABLE fixture_p (id INTEGER PRIMARY KEY)")
        db.execute("CREATE TABLE fixture_c (p INTEGER REFERENCES fixture_p(id) DEFERRABLE INITIALLY DEFERRED)")
    original, before = hive.ledger.append_locked, hive.ledger.head()

    def fail_commit(db, kind, *args, **kwargs):  # type: ignore[no-untyped-def]
        if kind == "goal.planned":
            db.execute("INSERT INTO fixture_c VALUES (99)")
        return original(db, kind, *args, **kwargs)

    with monkeypatch.context() as patch:
        patch.setattr(hive.ledger, "append_locked", fail_commit)
        with pytest.raises(sqlite3.IntegrityError):
            publish(hive)
    assert hive.ledger.head() == before and not list(hive.ledger.events(kind="egg.laid"))
    assert publish(hive).existing is False


def test_other_reader_sees_no_partial_publication(hive: Hive, monkeypatch: pytest.MonkeyPatch) -> None:
    with Hive.open(hive.root) as other:
        before, original = other.ledger.head(), hive.ledger.append_locked

        def observe(*args, **kwargs):  # type: ignore[no-untyped-def]
            number = original(*args, **kwargs)
            assert other.ledger.head() == before and not fold_eggs(other.ledger)
            return number

        monkeypatch.setattr(hive.ledger, "append_locked", observe)
        result = publish(hive, raw(task("a"), task("b", ("a",))))
        assert len(fold_eggs(other.ledger)) == 2 and other.ledger.head().seq == result.event_seq  # type: ignore[union-attr]


def test_uncertain_postcommit_completion_is_resolved_by_read_only_show(
    hive: Hive, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fail_readback(*args):  # type: ignore[no-untyped-def]
        raise OSError("fixture readback unavailable")

    with monkeypatch.context() as patch:
        patch.setattr(hive.ledger, "_post_write_fetch", fail_readback)
        with pytest.raises(OSError):
            publish(hive)
    before = hive.ledger.head()
    assert read_plan(hive, "goal_fixture").existing and hive.ledger.head() == before
    assert len(list(hive.ledger.events(kind="egg.laid"))) == 1


def test_corrupt_source_is_not_published_or_recovered(hive: Hive) -> None:
    publish(hive)
    with hive.ledger.transaction() as db:
        db.execute("UPDATE events SET payload=? WHERE kind='goal.planned'", (b"{}",))
    with pytest.raises(ChainBroken):
        read_plan(hive, "goal_fixture")
    with pytest.raises(ChainBroken):
        publish(hive)


def _cap(hive: Hive, egg_id: str):  # type: ignore[no-untyped-def]
    return hive.authority().issue(
        "worker:a", "egg:" + egg_id, Grant(providers=("scripted",), models=("fixture",), max_calls=3), 60000
    )


def test_fixture_graph_runs_through_claim_receipt_gate_and_capsule(hive: Hive) -> None:
    result = publish(hive, raw(task("b", ("a",)), task("a")), PlanBudget(2, 1024))
    w = Worker(hive, "a", providers=("scripted",), models=("fixture",))
    for egg in result.eggs:
        assert [v.egg_id for v in ready(fold_eggs(hive.ledger))] == [egg.egg_id]
        claim = w.claim()
        assert claim is not None and claim.egg.egg_id == egg.egg_id
        witnessed = Inference(hive).run(
            FixtureProvider("scripted", ['{"answer":"bee"}']),
            InferenceRequest("fixture", (Message("user", "fixture"),), max_tokens=8),
            w.actor,
            claim.capability,
        )
        verify_receipt(hive, witnessed.receipt)
        w.deliver(claim, {"answer": "bee"})
        assert Gate(hive).review(egg.egg_id).verdict == "hatched"
        assert build_capsule(hive, egg.egg_id).payload["next_step"] == "complete"
    spends = list(hive.ledger.events(kind="capability.spent"))
    assert len(spends) == 2 and sum(e.payload["plan"]["completion_tokens"] for e in spends) == 16
    assert all(e.payload["provider_kind"] == "fixture" for e in hive.ledger.events(kind="inference.receipt"))


def test_replacement_capability_does_not_reset_task_budget(hive: Hive) -> None:
    e = publish(hive).eggs[0]
    a, b = _cap(hive, e.egg_id), _cap(hive, e.egg_id)
    hive.authority().authorize_inference(a, "worker:a", "scripted", "fixture", 512)
    before = hive.ledger.head()
    with pytest.raises(AuthorityError, match="plan budget"):
        hive.authority().authorize_inference(b, "worker:a", "scripted", "fixture", 1)
    assert hive.ledger.head() == before


def test_task_profile_output_limit_is_not_enlarged_by_a_host_token(hive: Hive) -> None:
    e = publish(hive).eggs[0]
    before = hive.ledger.head()
    cap = _cap(hive, e.egg_id)
    with pytest.raises(AuthorityError, match="plan budget"):
        hive.authority().authorize_inference(cap, "worker:a", "scripted", "fixture", 513)
    assert not list(hive.ledger.events(kind="capability.spent")) and hive.ledger.head() != before


def test_unknown_provider_effect_consumes_plan_allowance(hive: Hive) -> None:
    e = publish(hive).eggs[0]
    cap = _cap(hive, e.egg_id)
    with pytest.raises(RuntimeError, match="no scripted replies"):
        Inference(hive).run(
            FixtureProvider("scripted", []),
            InferenceRequest("fixture", (Message("user", "fixture"),), max_tokens=8),
            "worker:a",
            cap,
        )
    assert not list(hive.ledger.events(kind="inference.receipt"))
    with pytest.raises(AuthorityError, match="plan budget"):
        hive.authority().authorize_inference(_cap(hive, e.egg_id), "worker:a", "scripted", "fixture", 8)


def test_unrecorded_prior_budget_charge_is_not_assumed_zero(hive: Hive) -> None:
    e = publish(hive).eggs[0]
    cap = _cap(hive, e.egg_id)
    hive.ledger.append(
        "capability.spent",
        "worker:a",
        {"action": {"type": "inference", "provider": "scripted", "model": "fixture"}, "n": 1, "token_id": cap.token_id},
    )
    with pytest.raises(AuthorityError, match="plan budget"):
        hive.authority().authorize_inference(cap, "worker:a", "scripted", "fixture", 1)


def test_appending_an_unplanned_task_cannot_borrow_the_goal_budget(hive: Hive) -> None:
    publish(hive)
    e = lay(hive, "goal_fixture", "diploid", {"q": "extra"}, SCHEMA)
    with pytest.raises(AuthorityError, match="plan budget"):
        hive.authority().authorize_inference(_cap(hive, e.egg_id), "worker:a", "scripted", "fixture", 1)


def test_competing_capabilities_share_one_lifetime_plan_allowance(hive: Hive) -> None:
    e = publish(hive, raw(task(ploidy="haploid")), PlanBudget(3, 3072)).eggs[0]
    barrier = threading.Barrier(4)
    root = hive.root

    def spend(_: int) -> str:
        with Hive.open(root) as other:
            cap = _cap(other, e.egg_id)
            barrier.wait(timeout=20)
            try:
                other.authority().authorize_inference(cap, "worker:a", "scripted", "fixture", 1024)
                return "spent"
            except AuthorityError:
                return "denied"

    with ThreadPoolExecutor(max_workers=4) as pool:
        outcomes = list(pool.map(spend, range(4)))
    assert outcomes.count("spent") == 3 and outcomes.count("denied") == 1
    spends = list(hive.ledger.events(kind="capability.spent"))
    assert sum(e.payload["plan"]["completion_tokens"] for e in spends) == 3072
    hive.ledger.verify_chain(require_signatures=True)


def test_allowlisted_tool_spend_counts_calls_without_completion_tokens(hive: Hive) -> None:
    e = publish(hive, raw(task(tools=["read_data"])), PlanBudget(1, 512, allowed_tools=("read_data",))).eggs[0]
    cap = hive.authority().issue("worker:a", "egg:" + e.egg_id, Grant(tools=("read_data",)), 60000)
    hive.authority().authorize_tool(cap, "worker:a", "read_data")
    spend = list(hive.ledger.events(kind="capability.spent"))[-1]
    assert spend.payload["plan"]["completion_tokens"] == 0
    with pytest.raises(AuthorityError):
        hive.authority().authorize_inference(_cap(hive, e.egg_id), "worker:a", "scripted", "fixture", 1)


def test_cli_validate_publish_show_has_no_implicit_execution(
    hive: Hive, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    from queen_os.cli import main

    p = tmp_path / "proposal.json"
    p.write_bytes(raw())
    before = hive.ledger.head()
    assert main(["plan", "validate", str(p), "--calls", "1", "--completion-tokens", "512"]) == 0
    assert json.loads(capsys.readouterr().out)["authority"] == "none" and hive.ledger.head() == before
    assert (
        main(
            [
                "plan",
                "publish",
                "goal_cli",
                str(p),
                "--calls",
                "1",
                "--completion-tokens",
                "512",
                "--objective",
                "fixture goal",
                "--hive",
                str(hive.root),
            ]
        )
        == 0
    )
    first = json.loads(capsys.readouterr().out)
    before = hive.ledger.head()
    assert main(["plan", "show", "goal_cli", "--hive", str(hive.root)]) == 0
    shown = json.loads(capsys.readouterr().out)
    assert shown["existing"] and shown["egg_ids"] == first["egg_ids"] and hive.ledger.head() == before
    assert not list(hive.ledger.events(kind="capability.issued"))


def test_numeric_canonical_expansion_cannot_publish_an_unreadable_plan(hive: Hive) -> None:
    nodes = [task("n" + str(i), input={"values": [1e20] * 300}) for i in range(6)]
    data = json.dumps({"v": 1, "tasks": nodes}, separators=(",", ":")).encode()
    assert len(data) < 32768 and len(canonicalize(json.loads(data))) > 32768
    before = hive.ledger.head()
    with pytest.raises(PlanError, match="canonical proposal byte limit"):
        publish(hive, data)
    assert hive.ledger.head() == before
