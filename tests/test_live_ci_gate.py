"""Workflow authorization tests using synthetic GitHub metadata, never inference."""

from __future__ import annotations

import runpy
from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest

authorize_dispatch = runpy.run_path(str(Path(__file__).resolve().parents[1] / "scripts" / "live_ci_gate.py"))[
    "authorize_dispatch"
]
SHA = "a" * 40


def metadata() -> tuple[dict[str, Any], dict[str, Any]]:
    event = {
        "inputs": {
            "confirm_live_inference": "true",
            "approved_commit_sha": SHA,
            "authorization_ref": "https://example.invalid/fixture-authorization",
            "provider": "ollama",
            "model": "fixture-model:small",
            "max_tokens": "24",
        }
    }
    environment = {
        "name": "live-inference",
        "protection_rules": [
            {
                "type": "required_reviewers",
                "prevent_self_review": True,
                "reviewers": [{"type": "User", "reviewer": {"id": 123}}],
            }
        ],
    }
    return event, environment


def test_complete_manual_scope_and_protected_environment_pass_preflight() -> None:
    event, environment = metadata()
    allowed = authorize_dispatch(event, "workflow_dispatch", "refs/heads/main", SHA, environment)
    assert allowed["model"] == "fixture-model:small" and allowed["max_tokens"] == "24"


@pytest.mark.parametrize("event_name", ["pull_request", "pull_request_target", "push", "schedule", "workflow_run"])
def test_automatic_events_never_admit_live_work(event_name: str) -> None:
    event, environment = metadata()
    with pytest.raises(ValueError, match="explicit dispatch"):
        authorize_dispatch(event, event_name, "refs/heads/main", SHA, environment)


@pytest.mark.parametrize("ref", ["refs/heads/feature", "refs/pull/3/merge", "refs/tags/main"])
def test_only_main_with_exact_approved_commit_is_eligible(ref: str) -> None:
    event, environment = metadata()
    with pytest.raises(ValueError):
        authorize_dispatch(event, "workflow_dispatch", ref, SHA, environment)


@pytest.mark.parametrize(
    ("field", "bad"),
    [
        ("confirm_live_inference", "false"),
        ("confirm_live_inference", True),
        ("approved_commit_sha", "b" * 40),
        ("authorization_ref", ""),
        ("provider", "unknown"),
        ("model", "$(touch unexpected)"),
        ("max_tokens", "129"),
        ("max_tokens", "01"),
    ],
)
def test_missing_or_conflicting_scope_is_refused(field: str, bad: Any) -> None:
    event, environment = metadata()
    event["inputs"][field] = bad
    with pytest.raises(ValueError):
        authorize_dispatch(event, "workflow_dispatch", "refs/heads/main", SHA, environment)


@pytest.mark.parametrize("mutation", ["absent", "unprotected", "self_review", "no_reviewers"])
def test_unverified_environment_cannot_become_an_approval_by_name(mutation: str) -> None:
    event, environment = metadata()
    environment = deepcopy(environment)
    if mutation == "absent":
        environment = {}
    elif mutation == "unprotected":
        environment["protection_rules"] = []
    elif mutation == "self_review":
        environment["protection_rules"][0]["prevent_self_review"] = False
    else:
        environment["protection_rules"][0]["reviewers"] = []
    with pytest.raises(ValueError):
        authorize_dispatch(event, "workflow_dispatch", "refs/heads/main", SHA, environment)


# -- standing-order mode (owner order SO-0001, QOS-0003) ---------------------------------

ORDER: dict[str, Any] = {
    "order_id": "SO-0001",
    "status": "active",
    "engineers": ["claude", "sage"],
    "scope": {"ollama": ["qwen2.5:*"], "anthropic": ["claude-haiku-*"]},
    "max_output_tokens": 128,
    "max_runs_per_utc_day": 20,
}


def standing(**inputs: Any) -> tuple[dict[str, Any], dict[str, Any]]:
    event = {
        "inputs": {
            "confirm_live_inference": "true",
            "approved_commit_sha": SHA,
            "authorization_ref": "standing-order:SO-0001",
            "engineer": "claude",
            "provider": "anthropic",
            "model": "claude-haiku-5-5",
            "max_tokens": "64",
            **inputs,
        }
    }
    return event, {"name": "live-inference", "protection_rules": []}


def test_standing_order_admits_in_scope_engineer_dispatch() -> None:
    event, env = standing()
    allowed = authorize_dispatch(event, "workflow_dispatch", "refs/heads/main", SHA, env, ORDER, 3)
    assert allowed["mode"] == "standing-order" and allowed["engineer"] == "claude"


@pytest.mark.parametrize(
    ("inputs", "order_patch", "runs", "why"),
    [
        ({"engineer": "owner"}, {}, 0, "not named"),
        ({"model": "claude-opus-5-5"}, {}, 0, "outside standing order"),
        ({"provider": "openai", "model": "gpt-5-mini"}, {}, 0, "outside standing order"),
        ({"max_tokens": "100"}, {"max_output_tokens": 64}, 0, "exceeds"),
        ({}, {}, 20, "budget"),
        ({}, {}, None, "fail closed"),
        ({}, {"status": "revoked"}, 0, "not active"),
        ({"authorization_ref": "standing-order:SO-0002"}, {}, 0, "not found"),
        ({}, {"__missing__": True}, 0, "not found"),
    ],
)
def test_standing_order_refusals(
    inputs: dict[str, Any], order_patch: dict[str, Any], runs: int | None, why: str
) -> None:
    event, env = standing(**inputs)
    order = None if order_patch.get("__missing__") else {**ORDER, **order_patch}
    with pytest.raises(ValueError, match=why):
        authorize_dispatch(event, "workflow_dispatch", "refs/heads/main", SHA, env, order, runs)


def test_standing_order_still_requires_main_exact_sha_and_confirmation() -> None:
    event, env = standing()
    with pytest.raises(ValueError):
        authorize_dispatch(event, "workflow_dispatch", "refs/heads/feature", SHA, env, ORDER, 0)
    with pytest.raises(ValueError):
        authorize_dispatch(event, "workflow_dispatch", "refs/heads/main", "b" * 40, env, ORDER, 0)
    event["inputs"]["confirm_live_inference"] = "false"
    with pytest.raises(ValueError):
        authorize_dispatch(event, "workflow_dispatch", "refs/heads/main", SHA, env, ORDER, 0)


def test_standing_order_rejects_deadlocking_environment() -> None:
    event, _ = standing()
    env = {
        "name": "live-inference",
        "protection_rules": [
            {
                "type": "required_reviewers",
                "prevent_self_review": True,
                "reviewers": [{"type": "User", "reviewer": {"id": 1}}],
            }
        ],
    }
    with pytest.raises(ValueError, match="deadlock"):
        authorize_dispatch(event, "workflow_dispatch", "refs/heads/main", SHA, env, ORDER, 0)


def test_repository_standing_order_is_well_formed() -> None:
    import json

    order = json.loads((Path(__file__).resolve().parents[1] / "governance" / "live_standing_order.json").read_text())
    assert order["order_id"] == "SO-0001" and order["status"] in {"active", "revoked"}
    assert set(order["engineers"]) <= {"claude", "sage"} and order["max_output_tokens"] <= 128
    assert set(order["scope"]) <= {"ollama", "anthropic", "openai", "gemini"}
