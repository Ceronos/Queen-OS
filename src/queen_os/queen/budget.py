"""Reserve a published plan's call/output allowance before an effect, under the writer lock."""

from __future__ import annotations

from typing import Any

from queen_os.comb.ledger import Ledger


class PlanBudgetError(ValueError):
    pass


def _cost(action: dict[str, Any], requested: int, maximum: int) -> int:
    if action.get("type") == "tool":
        if type(requested) is not int or requested != 0:
            raise PlanBudgetError("tool spend cannot declare completion tokens")
        return 0
    if action.get("type") != "inference" or type(requested) is not int or not 1 <= requested <= maximum:
        raise PlanBudgetError("invalid planned completion-token reservation")
    return requested


def plan_charge(ledger: Ledger, scope: str, action: dict[str, Any], completion_tokens: int) -> dict[str, Any] | None:
    """Called only within Authority._reserve's existing BEGIN IMMEDIATE transaction.

    Tokens are reserved request ceilings, not measured generation, input tokens, USD,
    energy or refunds. A failed/uncertain call consumes its reservation.
    """
    if not scope.startswith("egg:"):
        return None
    egg_id = scope[4:]
    egg = ledger.find_op("egg.laid:" + egg_id)
    if egg is None:
        return None  # legacy standalone capability scopes have no published plan
    ledger._check_event(egg)
    goal = egg.payload["goal_id"]
    plan = ledger.find_op("goal.planned:" + goal)
    if plan is None:
        return None
    ledger._check_event(plan)
    p = plan.payload
    if plan.kind != "goal.planned" or plan.actor != "queen:planner" or type(p.get("v")) is not int or p["v"] != 1:
        raise PlanBudgetError("unrecognized plan budget evidence")
    tasks = {n["egg_id"]: n for n in p["tasks"]}
    if egg_id not in tasks:
        raise PlanBudgetError("task is not part of its goal's published graph")
    proposed = {node["id"]: node for node in p["proposal"]["tasks"]}
    allowed_tools = proposed[tasks[egg_id]["local_id"]]["tools"]
    if action.get("type") == "tool" and action.get("tool") not in allowed_tools:
        raise PlanBudgetError("tool was not admitted for this task")
    cost = _cost(action, completion_tokens, tasks[egg_id]["max_output_tokens"])
    token_tasks = {}
    for event in ledger.events(kind="capability.issued"):
        scope_egg = event.payload.get("scope", "")[4:] if isinstance(event.payload.get("scope"), str) else ""
        if event.payload.get("scope") == "egg:" + scope_egg and scope_egg in tasks:
            ledger._check_event(event)
            token_tasks[event.payload["token_id"]] = scope_egg
    calls = reserved = task_calls = 0
    for event in ledger.events(kind="capability.spent"):
        spend = event.payload
        tag = spend.get("plan")
        related = spend.get("token_id") in token_tasks
        if not related and not (isinstance(tag, dict) and tag.get("goal_id") == goal):
            continue
        ledger._check_event(event)
        if (
            not related
            or not isinstance(tag, dict)
            or set(tag) != {"goal_id", "plan_hash", "egg_id", "completion_tokens"}
            or tag["goal_id"] != goal
            or tag["plan_hash"] != plan.hash
            or tag["egg_id"] != token_tasks[spend["token_id"]]
        ):
            raise PlanBudgetError("missing or inconsistent prior plan reservation")
        spent_egg = tag["egg_id"]
        reserved += _cost(spend["action"], tag["completion_tokens"], tasks[spent_egg]["max_output_tokens"])
        calls += 1
        task_calls += int(spent_egg == egg_id)
    limits = p["limits"]
    if (
        task_calls + 1 > tasks[egg_id]["max_calls"]
        or calls + 1 > limits["max_calls"]
        or reserved + cost > limits["max_completion_tokens"]
    ):
        raise PlanBudgetError("published task/goal call or completion-token budget exhausted")
    return {"goal_id": goal, "plan_hash": plan.hash, "egg_id": egg_id, "completion_tokens": cost}
