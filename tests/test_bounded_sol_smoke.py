"""Offline two-arm admission and signed mocked-HTTP evidence; no live requests."""

from __future__ import annotations

import json
import runpy
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
import pytest

from queen_os.hive import Hive
from queen_os.secrets import Secret

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
GATE = runpy.run_path(str(SCRIPTS / "bounded_sol_gate.py"))
SMOKE = runpy.run_path(str(SCRIPTS / "bounded_sol_smoke.py"))
NOW = datetime(2026, 11, 8, tzinfo=UTC)


def metadata() -> tuple[dict[str, str], dict[str, Any], dict[str, Any], dict[str, Any]]:
    return (
        {
            "GITHUB_EVENT_NAME": "workflow_dispatch",
            "GITHUB_REF": "refs/heads/main",
            "GITHUB_ACTOR": "Ceronos",
            "GITHUB_SHA": "a" * 40,
            "GITHUB_RUN_ATTEMPT": "1",
            "GITHUB_RUN_ID": "101",
        },
        {"inputs": {"approved_commit_sha": "a" * 40, "confirm_billable_sol": "true", "confirm_usd_005": "true"}},
        {"name": "live-inference", "protection_rules": []},
        {"total_count": 1, "workflow_runs": [{"id": 101}]},
    )


def test_one_owner_dispatch_passes_without_erasing_environment_protections() -> None:
    context, event, env, runs = metadata()
    env["protection_rules"] = [{"type": "required_reviewers", "prevent_self_review": True}]
    before = deepcopy(env)
    GATE["authorize"](context, event, env, runs, NOW)
    assert env == before  # GitHub still enforces any actual reviewer requirement


@pytest.mark.parametrize(
    "field,bad",
    [
        ("GITHUB_EVENT_NAME", "push"),
        ("GITHUB_REF", "refs/heads/feature"),
        ("GITHUB_ACTOR", "other"),
        ("GITHUB_RUN_ATTEMPT", "2"),
        ("GITHUB_SHA", "b" * 40),
        ("GITHUB_RUN_ID", "102"),
    ],
)
def test_wrong_context_never_admits(field: str, bad: str) -> None:
    context, event, env, runs = metadata()
    context[field] = bad
    with pytest.raises(ValueError):
        GATE["authorize"](context, event, env, runs, NOW)


@pytest.mark.parametrize(
    "field,bad", [("confirm_billable_sol", "false"), ("confirm_usd_005", True), ("approved_commit_sha", "b" * 40)]
)
def test_missing_exact_confirmation_never_admits(field: str, bad: Any) -> None:
    context, event, env, runs = metadata()
    event["inputs"][field] = bad
    with pytest.raises(ValueError):
        GATE["authorize"](context, event, env, runs, NOW)


@pytest.mark.parametrize(
    "runs",
    [
        {},
        {"total_count": 2, "workflow_runs": [{"id": 101}]},
        {"total_count": 2, "workflow_runs": [{"id": 100, "conclusion": "cancelled"}, {"id": 101}]},
        {"total_count": 2, "workflow_runs": [{"id": 101}, {"id": 101}]},
        {"total_count": 1, "workflow_runs": [{"id": True}]},
    ],
)
def test_unavailable_partial_duplicate_or_previously_used_history_refuses(runs: dict[str, Any]) -> None:
    context, event, env, _ = metadata()
    with pytest.raises(ValueError):
        GATE["authorize"](context, event, env, runs, NOW)


def test_environment_absence_and_expiry_refuse() -> None:
    context, event, env, runs = metadata()
    with pytest.raises(ValueError):
        GATE["authorize"](context, event, {}, runs, NOW)
    with pytest.raises(ValueError):
        GATE["authorize"](context, event, env, runs, datetime(2026, 11, 10, tzinfo=UTC))


def envelope(text: str = '{"answer":"QOS-CANARY-OK"}') -> dict[str, Any]:
    return {
        "model": "gpt-6.1-sol",
        "choices": [{"finish_reason": "stop", "message": {"content": text}}],
        "usage": {"prompt_tokens": 100, "completion_tokens": 20},
    }


def test_fixed_wire_one_attempt_fixture_custody_no_private_export_and_offline_replay(tmp_path: Path) -> None:
    p = SMOKE["SolProvider"](Secret("fixture-only-key-not-a-live-credential"))
    p.kind = "fixture"
    calls = []

    def respond(request: httpx.Request) -> httpx.Response:
        calls.append(json.loads(request.content))
        return httpx.Response(200, json=envelope())

    h = Hive.init(tmp_path / "h", "sol_fixture", mode="test")
    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        report = SMOKE["witness"](h, p, client, tmp_path / "out")
    assert report["path"] == "VERIFIED" and report["fixture"] is True and report["semantic_match"] is True
    assert len(calls) == 1
    body = calls[0]
    assert body["model"] == "gpt-6.1-sol" and body["max_completion_tokens"] == 1024
    assert body["reasoning_effort"] == "low" and body["service_tier"] == "default" and body["store"] is False
    assert not {"temperature", "tools", "tool_choice", "previous_response_id"} & set(body)
    assert not any(f.suffix == ".pem" or "vault" in f.parts for f in (tmp_path / "out").rglob("*"))
    assert SMOKE["replay"](tmp_path / "out")["fixture"] is True
    assert len(calls) == 1  # replay made no transport request


@pytest.mark.parametrize(
    "status,text",
    [
        (400, '{"answer":"QOS-CANARY-OK"}'),
        (200, "not JSON"),
        (200, '{"answer":true}'),
        (200, '{"answer":"x","extra":1}'),
    ],
)
def test_received_rejection_is_retained_and_never_replays_as_success(tmp_path: Path, status: int, text: str) -> None:
    p = SMOKE["SolProvider"](Secret("fixture-only-key-not-a-live-credential"))
    p.kind = "fixture"
    calls = []

    def respond(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(status, json=envelope(text))

    h = Hive.init(tmp_path / "h", "sol_fixture", mode="test")
    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        report = SMOKE["witness"](h, p, client, tmp_path / "out")
    assert report["path"] == "REJECTED" and len(calls) == 1
    assert report["events_verified"] == 4
    with pytest.raises(PermissionError):
        SMOKE["replay"](tmp_path / "out")


def test_wrong_answer_is_separate_from_valid_schema_and_path(tmp_path: Path) -> None:
    p = SMOKE["SolProvider"](Secret("fixture-only-key-not-a-live-credential"))
    p.kind = "fixture"
    h = Hive.init(tmp_path / "h", "sol_fixture", mode="test")
    transport = httpx.MockTransport(lambda _: httpx.Response(200, json=envelope('{"answer":"wrong"}')))
    with httpx.Client(transport=transport) as c:
        report = SMOKE["witness"](h, p, c, tmp_path / "out")
    assert report["path"] == "VERIFIED" and report["semantic_match"] is False


def test_transport_failure_has_no_fabricated_receipt_and_no_retry(tmp_path: Path) -> None:
    calls = []
    p = SMOKE["SolProvider"](Secret("fixture-only-key-not-a-live-credential"))
    p.kind = "fixture"

    def fail(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        raise httpx.ReadTimeout("fixture timeout")

    h = Hive.init(tmp_path / "h", "sol_fixture", mode="test")
    with httpx.Client(transport=httpx.MockTransport(fail)) as c:
        report = SMOKE["witness"](h, p, c, tmp_path / "out")
    assert report["path"] == "TRANSPORT_OR_PROVIDER_FAILURE" and len(calls) == 1 and report["events_verified"] == 3
    with pytest.raises(ValueError):
        SMOKE["replay"](tmp_path / "out")


@pytest.mark.parametrize("usage", [None, {"prompt_tokens": 100, "completion_tokens": 1025}])
def test_missing_or_excess_usage_cannot_be_a_success(tmp_path: Path, usage: Any) -> None:
    p = SMOKE["SolProvider"](Secret("fixture-only-key-not-a-live-credential"))
    p.kind = "fixture"
    data = envelope()
    data["usage"] = usage
    h = Hive.init(tmp_path / "h", "sol_fixture", mode="test")
    with httpx.Client(transport=httpx.MockTransport(lambda _: httpx.Response(200, json=data))) as c:
        report = SMOKE["witness"](h, p, c, tmp_path / "out")
    assert report["path"] == "USAGE_UNVERIFIED_OR_OVER_LIMIT"
    with pytest.raises(ValueError):
        SMOKE["replay"](tmp_path / "out")


def test_production_fixture_refuses_without_contacting_transport(tmp_path: Path) -> None:
    p = SMOKE["SolProvider"](Secret("fixture-only-key-not-a-live-credential"))
    p.kind = "fixture"
    calls = []
    with Hive.init(tmp_path / "h", "sol_production") as h:
        with (
            httpx.Client(transport=httpx.MockTransport(lambda req: calls.append(req))) as c,
            pytest.raises(PermissionError),
        ):
            SMOKE["witness"](h, p, c, tmp_path / "out")
        assert not calls and len(list(h.ledger.events())) == 2
