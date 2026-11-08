"""Host-validated goal-to-TaskEgg publication. Proposals are inert, never grants."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from queen_os.comb.ledger import IdempotencyConflict
from queen_os.hive import Hive
from queen_os.providers.structured import JsonSchemaOutput, strict_json
from queen_os.queen.egg import LAID, TaskEgg, load, validate_shape
from queen_os.queen.valve import profile_for
from queen_os.serial.afser import sha256_hex
from queen_os.serial.jcs import canonicalize

PLANNED = "goal.planned"
MAX_PROPOSAL_BYTES = 32_768
MAX_TASKS = 32
MAX_EDGES = 128
MAX_DEPTH = 8
_LOCAL_ID = re.compile(r"[a-z][a-z0-9_]{0,31}")
_GOAL_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,63}")


class PlanError(ValueError):
    """Invalid, unsupported, inconsistent or over-budget proposal; no repair."""


@dataclass(frozen=True)
class PlanBudget:
    max_calls: int
    max_completion_tokens: int
    max_tasks: int = 16
    allowed_tools: tuple[str, ...] = ()

    def to_json(self) -> dict[str, Any]:
        return {
            "max_calls": self.max_calls,
            "max_completion_tokens": self.max_completion_tokens,
            "max_tasks": self.max_tasks,
            "allowed_tools": list(self.allowed_tools),
        }


@dataclass(frozen=True)
class ValidatedPlan:
    raw: bytes
    order: tuple[str, ...]
    calls: int
    completion_tokens: int

    @property
    def proposal(self) -> dict[str, Any]:
        return dict(strict_json(self.raw))


@dataclass(frozen=True)
class PublishedPlan:
    goal_id: str
    proposal_sha256: str
    eggs: tuple[TaskEgg, ...]
    event_seq: int
    existing: bool


def validate_proposal(raw: bytes, budget: PlanBudget) -> ValidatedPlan:
    """Pure validation; even a directly constructed ValidatedPlan grants nothing."""
    try:
        return _validate(raw, budget)
    except PlanError:
        raise
    except (ValueError, TypeError, KeyError, AttributeError, RecursionError) as exc:
        raise PlanError("invalid task graph or host budget") from exc


def _validate(raw: bytes, budget: PlanBudget) -> ValidatedPlan:
    if not isinstance(raw, bytes) or not 0 < len(raw) <= MAX_PROPOSAL_BYTES:
        raise PlanError("proposal byte limit")
    if any(
        type(value) is not int or not 1 <= value <= bound
        for value, bound in [
            (budget.max_calls, 10_000),
            (budget.max_completion_tokens, 1_048_576),
            (budget.max_tasks, MAX_TASKS),
        ]
    ):
        raise PlanError("host budget requires bounded positive integers")
    if (
        not isinstance(budget.allowed_tools, tuple)
        or len(budget.allowed_tools) > 16
        or any(not isinstance(t, str) or not t.isidentifier() for t in budget.allowed_tools)
        or len(set(budget.allowed_tools)) != len(budget.allowed_tools)
    ):
        raise PlanError("invalid host tool allowlist")
    value = strict_json(raw.decode("utf-8"))
    if (
        not isinstance(value, dict)
        or set(value) != {"v", "tasks"}
        or type(value["v"]) is not int
        or value["v"] != 1
        or not isinstance(value["tasks"], list)
        or not 1 <= len(value["tasks"]) <= budget.max_tasks
    ):
        raise PlanError("unsupported proposal shape or task count")
    canonical = canonicalize(value)
    if len(canonical) > MAX_PROPOSAL_BYTES:
        raise PlanError("canonical proposal byte limit")
    nodes: dict[str, dict[str, Any]] = {}
    calls = tokens = 0
    for node in value["tasks"]:
        if not isinstance(node, dict) or set(node) != {
            "id",
            "ploidy",
            "input",
            "schema",
            "tools",
            "stimulus",
            "parents",
        }:
            raise PlanError("task fields differ from the proposal contract")
        ident = node["id"]
        if not isinstance(ident, str) or not _LOCAL_ID.fullmatch(ident) or ident in nodes:
            raise PlanError("invalid or duplicate local task id")
        if (
            not isinstance(node["parents"], list)
            or len(node["parents"]) > 16
            or any(not isinstance(p, str) for p in node["parents"])
            or len(set(node["parents"])) != len(node["parents"])
            or not isinstance(node["tools"], list)
            or any(not isinstance(t, str) or t not in budget.allowed_tools for t in node["tools"])
            or len(set(node["tools"])) != len(node["tools"])
            or type(node["stimulus"]) not in (int, float)
            or not isinstance(node["schema"], dict)
        ):
            raise PlanError("invalid parents, tools, stimulus or schema")
        # Require a portable, closed, reference-free output contract in this M1 slice.
        JsonSchemaOutput(node["schema"])
        egg = TaskEgg(
            ident,
            "proposal",
            node["ploidy"],
            node["input"],
            node["schema"],
            tuple(node["tools"]),
            node["stimulus"],
            tuple(node["parents"]),
        )
        validate_shape(egg)
        profile = profile_for(egg)
        if profile.quorum:
            raise PlanError("task requires unavailable M2 quorum")
        calls += profile.max_calls
        tokens += profile.max_calls * profile.max_output_tokens
        nodes[ident] = node
    if calls > budget.max_calls or tokens > budget.max_completion_tokens:
        raise PlanError("planned profiles exceed the host call/completion-token budget")
    if sum(len(n["parents"]) for n in nodes.values()) > MAX_EDGES:
        raise PlanError("graph edge limit")
    if any(p not in nodes for n in nodes.values() for p in n["parents"]):
        raise PlanError("dangling parent or external dependency")
    remaining = set(nodes)
    order: list[str] = []
    depths: dict[str, int] = {}
    while remaining:
        layer = sorted(i for i in remaining if all(p in depths for p in nodes[i]["parents"]))
        if not layer:
            raise PlanError("cyclic task graph")
        for ident in layer:
            depths[ident] = max((depths[p] + 1 for p in nodes[ident]["parents"]), default=0)
            if depths[ident] > MAX_DEPTH:
                raise PlanError("graph depth limit")
            order.append(ident)
            remaining.remove(ident)
    return ValidatedPlan(canonical, tuple(order), calls, tokens)


def _prepare(
    hive: Hive, goal_id: str, raw: bytes, budget: PlanBudget, objective: str
) -> tuple[dict[str, Any], tuple[TaskEgg, ...]]:
    if not isinstance(goal_id, str) or not _GOAL_ID.fullmatch(goal_id):
        raise PlanError("invalid host goal id")
    if not isinstance(objective, str) or not objective.strip() or len(canonicalize(objective)) > 8_000:
        raise PlanError("host objective must be a nonempty bounded string")
    plan = validate_proposal(raw, budget)
    from queen_os.queen.planner import validate_bound_proposal

    validate_bound_proposal(hive, goal_id, plan.raw, budget, objective)
    signer = hive.ledger.signer
    if signer is None:
        raise PlanError("publication requires the host signer")
    digest = sha256_hex(plan.raw)
    nodes = {n["id"]: n for n in plan.proposal["tasks"]}
    ids = {ident: "egg_" + sha256_hex(canonicalize([goal_id, digest, ident]))[:32] for ident in plan.order}
    eggs = []
    for ident in plan.order:
        n = nodes[ident]
        egg = TaskEgg(
            ids[ident],
            goal_id,
            n["ploidy"],
            n["input"],
            n["schema"],
            tuple(n["tools"]),
            float(n["stimulus"]),
            tuple(ids[p] for p in n["parents"]),
            signer.key_id,
        )
        validate_shape(egg)
        eggs.append(TaskEgg(**{**egg.__dict__, "signature": signer.sign(canonicalize(egg.body()))}))
    payload = {
        "v": 1,
        "goal_id": goal_id,
        "objective": objective,
        "objective_sha256": sha256_hex(canonicalize(objective)),
        "proposal_sha256": digest,
        "proposal": plan.proposal,
        "limits": budget.to_json(),
        "planned": {"calls": plan.calls, "completion_tokens": plan.completion_tokens},
        "tasks": [
            {
                "local_id": ident,
                "egg_id": egg.egg_id,
                "max_calls": profile_for(egg).max_calls,
                "max_output_tokens": profile_for(egg).max_output_tokens,
            }
            for ident, egg in zip(plan.order, eggs, strict=True)
        ],
    }
    if len(canonicalize(payload)) > 65_536:
        raise PlanError("publication record byte limit")
    return payload, tuple(eggs)


def _existing(hive: Hive, payload: dict[str, Any], eggs: tuple[TaskEgg, ...]) -> PublishedPlan:
    event = hive.ledger.find_op(f"{PLANNED}:{payload['goal_id']}")
    if event is None:
        raise PlanError("no published plan")
    hive.ledger._check_event(event)
    if event.kind != PLANNED or event.actor != "queen:planner" or canonicalize(event.payload) != canonicalize(payload):
        raise IdempotencyConflict("goal id already binds a different plan, budget or publisher")
    for egg in eggs:
        laid = hive.ledger.find_op(f"{LAID}:{egg.egg_id}")
        if laid is None:
            raise PlanError("published task evidence is missing")
        hive.ledger._check_event(laid)
        if (
            laid.kind != LAID
            or laid.actor != "queen:planner"
            or canonicalize(load(hive, egg.egg_id).to_json()) != canonicalize(egg.to_json())
        ):
            raise PlanError("published task differs from the accepted plan")
    return PublishedPlan(payload["goal_id"], payload["proposal_sha256"], eggs, event.seq, True)


def publish_plan(hive: Hive, goal_id: str, raw: bytes, budget: PlanBudget, *, objective: str) -> PublishedPlan:
    """Validate everything before one atomic signed append; stable goal id is the dedup key."""
    payload, eggs = _prepare(hive, goal_id, raw, budget, objective)
    sequences = []
    with hive.ledger.transaction() as db:
        hive.ledger.verify_chain(require_signatures=True)
        if hive.ledger.find_op(f"{PLANNED}:{goal_id}") is not None:
            return _existing(hive, payload, eggs)
        if db.execute(
            "SELECT 1 FROM events WHERE kind=? AND json_extract(payload,'$.goal_id')=?", (LAID, goal_id)
        ).fetchone():
            raise PlanError("goal already has standalone task history")
        for egg in eggs:
            if hive.ledger.find_op(f"{LAID}:{egg.egg_id}") is not None:
                raise PlanError("task id collision")
            sequences.append(
                hive.ledger.append_locked(db, LAID, "queen:planner", egg.to_json(), op_id=f"{LAID}:{egg.egg_id}")
            )
        seq = hive.ledger.append_locked(db, PLANNED, "queen:planner", payload, op_id=f"{PLANNED}:{goal_id}")
    # Failure here means publication may have committed. Read the goal before any new operation.
    for number in [*sequences, seq]:
        hive.ledger._post_write_fetch(number)
    return PublishedPlan(goal_id, payload["proposal_sha256"], eggs, seq, False)


def read_plan(hive: Hive, goal_id: str) -> PublishedPlan:
    """Read back a publication after uncertain completion; never re-execute its writes."""
    if not isinstance(goal_id, str) or not _GOAL_ID.fullmatch(goal_id):
        raise PlanError("invalid host goal id")
    with hive.ledger.read_snapshot():
        hive.ledger.verify_chain(require_signatures=True)
        event = hive.ledger.find_op(f"{PLANNED}:{goal_id}")
        if event is None:
            raise PlanError("no published plan")
        p = event.payload
        limits = p["limits"]
        budget = PlanBudget(
            limits["max_calls"], limits["max_completion_tokens"], limits["max_tasks"], tuple(limits["allowed_tools"])
        )
        payload, eggs = _prepare(hive, goal_id, canonicalize(p["proposal"]), budget, p["objective"])
        return _existing(hive, payload, eggs)
