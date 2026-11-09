"""Fixed planning/worker allocations in the same pre-effect authority transaction."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from queen_os.comb.ledger import Event, Ledger

RUN = "goal.run_prepared"
SOURCE = "goal.plan_source"


class RunBudgetError(ValueError):
    pass


@dataclass(frozen=True)
class RunBudget:
    max_calls: int = 4
    max_completion_tokens: int = 2560
    max_tasks: int = 3
    planner_output_tokens: int = 1024

    def validate(self) -> None:
        for value, low, high in [
            (self.max_tasks, 2, 3),
            (self.planner_output_tokens, 128, 2048),
            (self.max_calls, 1, 4),
            (self.max_completion_tokens, 1, 3584),
        ]:
            if type(value) is not int or not low <= value <= high:
                raise RunBudgetError("invalid fixed run allocation")
        if (
            self.max_calls < 1 + self.max_tasks
            or self.max_completion_tokens < self.planner_output_tokens + 512 * self.max_tasks
        ):
            raise RunBudgetError("planning and worker allocations exceed the run ceiling")

    def to_json(self) -> dict[str, int]:
        return {
            "max_calls": self.max_calls,
            "max_completion_tokens": self.max_completion_tokens,
            "max_tasks": self.max_tasks,
            "planner_output_tokens": self.planner_output_tokens,
        }

    @classmethod
    def from_json(cls, value: dict[str, Any]) -> RunBudget:
        if not isinstance(value, dict) or set(value) != {
            "max_calls",
            "max_completion_tokens",
            "max_tasks",
            "planner_output_tokens",
        }:
            raise RunBudgetError("unknown run allocation")
        budget = cls(**value)
        budget.validate()
        return budget


def read_run(ledger: Ledger, goal_id: str) -> Event:
    run = ledger.find_op(f"{RUN}:{goal_id}")
    if run is None:
        raise RunBudgetError("planning run is not prepared")
    ledger._check_event(run)
    if (
        run.kind != RUN
        or run.actor != "queen:planner"
        or run.payload.get("goal_id") != goal_id
        or type(run.payload.get("v")) is not int
        or run.payload["v"] != 1
    ):
        raise RunBudgetError("unrecognized planning run")
    RunBudget.from_json(run.payload["budget"])
    return run


def run_charge(
    ledger: Ledger,
    scope: str,
    action: dict[str, Any],
    completion_tokens: int,
    *,
    token_id: str | None = None,
    actor: str | None = None,
) -> dict[str, Any] | None:
    """Reserve requested ceilings, not measured usage; no pool borrowing or refunds."""
    if scope.startswith("planner:"):
        goal_id, phase = scope[8:], "planning"
    elif scope.startswith("egg:"):
        egg = ledger.find_op("egg.laid:" + scope[4:])
        if egg is None:
            return None
        ledger._check_event(egg)
        goal_id, phase = egg.payload["goal_id"], "workers"
        if ledger.find_op(f"{RUN}:{goal_id}") is None:
            return None  # Existing standalone/published goals retain their contract.
    else:
        return None
    run = read_run(ledger, goal_id)
    p, budget = run.payload, RunBudget.from_json(run.payload["budget"])
    if action != {"type": "inference", "provider": p["provider"], "model": p["model"]}:
        raise RunBudgetError("run permits only its exact provider/model and no tools")
    maximum = budget.planner_output_tokens if phase == "planning" else 512
    if type(completion_tokens) is not int or not 1 <= completion_tokens <= maximum:
        raise RunBudgetError("run output reservation refused")
    tasks: set[str] = set()
    plan = ledger.find_op("goal.planned:" + goal_id)
    if plan is not None:
        ledger._check_event(plan)
        tasks = {t["egg_id"] for t in plan.payload["tasks"]}
    if phase == "workers":
        source = ledger.find_op(f"{SOURCE}:{goal_id}")
        if plan is None or source is None or scope[4:] not in tasks:
            raise RunBudgetError("worker run has no source-bound publication")
        ledger._check_event(source)
        if (
            source.kind != SOURCE
            or source.actor != "queen:planner"
            or source.payload["run_hash"] != run.hash
            or source.payload["compiled_sha256"] != plan.payload["proposal_sha256"]
        ):
            raise RunBudgetError("worker publication/source mismatch")
    tokens: dict[str, str] = {}
    scopes: dict[str, str] = {}
    for event in ledger.events(kind="capability.issued"):
        cap_scope = event.payload.get("scope")
        if cap_scope == "planner:" + goal_id or cap_scope in {"egg:" + t for t in tasks}:
            ledger._check_event(event)
            tokens[event.payload["token_id"]] = "planning" if cap_scope == "planner:" + goal_id else "workers"
            scopes[event.payload["token_id"]] = cap_scope
    if phase == "workers":
        prepared = ledger.find_op("worker.request_prepared:" + scope[4:])
        if prepared is None:
            raise RunBudgetError("worker requires a frozen capsule-derived request")
        ledger._check_event(prepared)
        q = prepared.payload
        row = ledger._db.execute("SELECT holder, token, expires_ms FROM leases WHERE resource=?", (scope,)).fetchone()
        claims = [e for e in ledger.events(kind="egg.claimed") if e.payload.get("egg_id") == scope[4:]]
        if (
            prepared.kind != "worker.request_prepared"
            or prepared.actor != actor
            or q["token_id"] != token_id
            or q["run_hash"] != run.hash
            or completion_tokens != 512
            or row is None
            or row[0] != actor
            or row[1] != q["lease_token"]
            or row[2] != q["lease_expires_ms"]
            or row[2] <= ledger.now()
            or not claims
            or claims[-1].actor != actor
            or claims[-1].payload["token_id"] != token_id
            or ledger.find_op("egg.delivered:" + scope[4:]) is not None
            or ledger.find_op("egg.purged:" + scope[4:]) is not None
        ):
            raise RunBudgetError("prepared worker claim/fence is no longer current")
    calls, reserved = {"planning": 0, "workers": 0}, {"planning": 0, "workers": 0}
    for event in ledger.events(kind="capability.spent"):
        tag = event.payload.get("run")
        related = event.payload.get("token_id") in tokens
        if not related and not (isinstance(tag, dict) and tag.get("goal_id") == goal_id):
            continue
        ledger._check_event(event)
        if phase == "workers" and scopes.get(event.payload.get("token_id", "")) == scope:
            raise RunBudgetError("task allowance already spent; replacement claims cannot retry")
        expected_phase = tokens.get(event.payload.get("token_id", ""))
        if (
            not related
            or not isinstance(tag, dict)
            or set(tag) != {"goal_id", "run_hash", "phase", "completion_tokens"}
            or tag["goal_id"] != goal_id
            or tag["run_hash"] != run.hash
            or tag["phase"] != expected_phase
        ):
            raise RunBudgetError("missing or inconsistent run reservation")
        cap_max = budget.planner_output_tokens if expected_phase == "planning" else 512
        if (
            type(tag["completion_tokens"]) is not int
            or not 1 <= tag["completion_tokens"] <= cap_max
            or event.payload["action"] != action
        ):
            raise RunBudgetError("invalid prior run reservation")
        calls[tag["phase"]] += 1
        reserved[tag["phase"]] += tag["completion_tokens"]
    calls[phase] += 1
    reserved[phase] += completion_tokens
    if (
        calls["planning"] > 1
        or calls["workers"] > budget.max_tasks
        or reserved["planning"] > budget.planner_output_tokens
        or reserved["workers"] > 512 * budget.max_tasks
        or sum(calls.values()) > budget.max_calls
        or sum(reserved.values()) > budget.max_completion_tokens
    ):
        raise RunBudgetError("fixed run allocation exhausted")
    return {"goal_id": goal_id, "run_hash": run.hash, "phase": phase, "completion_tokens": completion_tokens}
