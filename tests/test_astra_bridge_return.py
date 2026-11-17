"""Fixture-only fault tests for the bounded connector relay; no model or network calls."""

import argparse
import copy
import hashlib
import importlib.util
import sys
import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import patch

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
SPEC = importlib.util.spec_from_file_location("astra_bridge_return", SCRIPTS / "astra_bridge_return.py")
assert SPEC and SPEC.loader
# Import the sibling without relying on a global Python search-path modification.
PROBE_SPEC = importlib.util.spec_from_file_location("astra_bridge_probe", SCRIPTS / "astra_bridge_probe.py")
assert PROBE_SPEC and PROBE_SPEC.loader
probe = importlib.util.module_from_spec(PROBE_SPEC)
PROBE_SPEC.loader.exec_module(probe)
with patch.dict(sys.modules, {"astra_bridge_probe": probe}):
    bridge = importlib.util.module_from_spec(SPEC)
    SPEC.loader.exec_module(bridge)

NOW = datetime(2026, 11, 17, 21, 0, tzinfo=UTC)
HANDOFF = "SAGE-BRIDGE-20261117-194755Z"


def issue():
    return {
        "number": 32,
        "state": "open",
        "title": probe.TITLE,
        "user": bridge.ACCOUNT.copy(),
        "created_at": "2026-11-16T18:56:32Z",
        "body": probe.MARKER
        + "\n"
        + probe.canonical(
            {
                "protocol": probe.PROTOCOL,
                "kind": "probe",
                "request_id": "fixture-001",
                "expires_at": "2026-11-22T00:00:00Z",
            }
        ),
    }


def prepared():
    with patch.object(probe, "gpu_summary", return_value={"status": "unavailable"}):
        return bridge.prepare(issue(), "fixture-001", HANDOFF, NOW)


def comment(body, *, comment_id=100):
    return {
        "id": comment_id,
        "body": body,
        "user": bridge.ACCOUNT.copy(),
        "html_url": f"https://github.com/{probe.REPO}/issues/32#issuecomment-{comment_id}",
        "created_at": "2026-11-17T21:00:01Z",
        "updated_at": "2026-11-17T21:00:01Z",
    }


def find(body, comments):
    return bridge.find_exact(body, comments, marker=bridge.MARKER, issue_number=32, request_id="fixture-001")


def test_export_is_bounded_and_binds_request_source_handoff():
    body = prepared()
    value = bridge.validate_return(body, issue(), NOW)
    assert len(body.encode()) < bridge.LIMIT
    assert value["scope"] == bridge.SCOPE
    assert value["handoff_marker"] == HANDOFF
    assert value["request_body_sha256"] == hashlib.sha256(issue()["body"].encode()).hexdigest()
    assert (
        value["source_sha256"]["astra_bridge_probe.py"]
        == hashlib.sha256((SCRIPTS / "astra_bridge_probe.py").read_bytes()).hexdigest()
    )
    assert value["probe_receipt"]["attestation"] == "none; producer self-report only"
    assert "not host or Sage identity" in value["provenance"]


@pytest.mark.parametrize(
    "change",
    [
        {"command": "run-shell"},
        {"scope": "run-model"},
        {"repository": "evil/repo"},
        {"request_id": "other"},
        {"issue_number": True},
        {"request_body_sha256": "0" * 64},
        {"posting_account": {"login": "Ceronos", "id": 1}},
        {"handoff_marker": "../escape"},
        {"source_sha256": {}},
        {"provenance": "authenticated Sage"},
    ],
)
def test_unknown_fields_scope_and_binding_fail_closed(change):
    value = bridge.decode(prepared(), bridge.MARKER) | change
    with pytest.raises(ValueError):
        bridge.validate_return(bridge.MARKER + "\n" + probe.canonical(value), issue(), NOW)


@pytest.mark.parametrize(
    "change",
    [
        {"hostname": "private-host"},
        {"gpu": {"status": "unavailable", "serial": "private"}},
        {"gpu": {"status": "detected", "devices": [{"name": "GPU", "memory_mib": True}]}},
        {"gpu": {"status": "detected", "devices": [{"name": "GPU", "memory_mib": 100, "serial": "private"}]}},
        {"architecture": "$(id)"},
        {"python": "secret-value"},
        {"os": "private-host"},
    ],
)
def test_probe_field_allowlist_before_export(change):
    value = bridge.decode(prepared(), bridge.MARKER)
    value["probe_receipt"]["result"].update(change)
    value["probe_receipt"]["result_sha256"] = bridge.digest(value["probe_receipt"]["result"])
    with pytest.raises(ValueError):
        bridge.validate_return(bridge.MARKER + "\n" + probe.canonical(value), issue(), NOW)


@pytest.mark.parametrize(
    "field,value",
    [
        ("result_sha256", "0" * 64),
        ("observed_at", "2026-11-15T00:00:00Z"),
        ("observed_at", "2026-11-18T00:00:00Z"),
        ("observed_at", "2026-11-17T21:00:00+00:00"),
        ("attestation", "verified Astra"),
        ("issue_number", 33),
        ("kind", "run_shell"),
    ],
)
def test_probe_digest_time_and_identity_fail_closed(field, value):
    envelope = bridge.decode(prepared(), bridge.MARKER)
    envelope["probe_receipt"][field] = value
    with pytest.raises(ValueError):
        bridge.validate_return(bridge.MARKER + "\n" + probe.canonical(envelope), issue(), NOW)


def test_expired_closed_changed_and_wrong_author_requests_fail_closed():
    body = prepared()
    for candidate in (
        issue() | {"state": "closed"},
        issue() | {"user": {"login": "other", "id": 1}},
        issue() | {"user": {"login": "Ceronos", "id": 1}},
    ):
        with pytest.raises(ValueError):
            bridge.validate_return(body, candidate, NOW)
    with pytest.raises(ValueError):
        bridge.validate_return(body, issue(), NOW + timedelta(days=6))
    changed = issue()
    changed["body"] += " "
    with pytest.raises(ValueError):
        bridge.validate_return(body, changed, NOW)
    with pytest.raises(ValueError):
        bridge.prepare(issue(), "other-request", HANDOFF, NOW)


def test_duplicate_json_and_oversize_are_refused():
    body = prepared()
    with pytest.raises(ValueError):
        bridge.decode(body.replace('"scope":', '"scope":"ignored","scope":'), bridge.MARKER)
    with pytest.raises(ValueError):
        bridge.decode(bridge.MARKER + "\n" + " " * bridge.LIMIT, bridge.MARKER)


def test_exact_readback_and_repeated_readback_have_no_write_effects():
    body = prepared()
    posted = comment(body)
    assert find(body, [posted]) == posted
    assert find(body, [posted]) == posted
    for comments in ([], [posted, copy.deepcopy(posted)], [posted, comment(body + " ", comment_id=101)]):
        with pytest.raises(ValueError):
            find(body, comments)


@pytest.mark.parametrize(
    "change",
    [
        {"user": {"login": "Ceronos", "id": 1}},
        {"user": {"login": "other", "id": 202629591}},
        {"html_url": "https://github.com/evil/repo/issues/32#issuecomment-100"},
        {"updated_at": "2026-11-17T21:01:00Z"},
        {"id": True},
        {"created_at": None},
    ],
)
def test_spoofed_edited_or_wrong_repository_comments_fail_closed(change):
    body = prepared()
    with pytest.raises(ValueError):
        find(body, [comment(body) | change])


def test_reverse_ack_binds_exact_comment_and_full_body_digest():
    body = prepared()
    value = bridge.validate_return(body, issue(), NOW)
    posted = find(body, [comment(body)])
    ack = bridge.acknowledgment(value, body, posted)
    data = bridge.decode(ack, bridge.ACK_MARKER)
    assert data["receipt_comment_id"] == 100
    assert data["receipt_body_sha256"] == hashlib.sha256(body.encode()).hexdigest()
    assert "Sage session identity not attested" in data["provenance"]
    assert (
        bridge.find_exact(
            ack, [comment(ack, comment_id=101)], marker=bridge.ACK_MARKER, issue_number=32, request_id="fixture-001"
        )["id"]
        == 101
    )
    bad = ack.replace('"receipt_comment_id":100', '"receipt_comment_id":99')
    with pytest.raises(ValueError):
        bridge.find_exact(ack, [comment(bad)], marker=bridge.ACK_MARKER, issue_number=32, request_id="fixture-001")


def test_cli_prepare_verify_ack_roundtrip_and_exclusive_export():
    current = issue()
    args = argparse.Namespace(command="prepare", issue=32, request_id="fixture-001", handoff_marker=HANDOFF)
    with (
        tempfile.TemporaryDirectory() as directory,
        patch.object(probe, "github_cli") as gh,
        patch.object(probe, "gpu_summary", return_value={"status": "unavailable"}),
    ):
        args.output = Path(directory) / "receipt.txt"
        with (
            patch.object(probe, "github_read", return_value=current),
            patch.object(bridge, "datetime", wraps=datetime) as clock,
        ):
            clock.now.return_value = NOW
            assert bridge.run(args) == 0
            with pytest.raises(FileExistsError):
                bridge.run(args)
        body = args.output.read_text()
        posted = comment(body)
        value = bridge.validate_return(body, current, NOW)
        ack = comment(bridge.acknowledgment(value, body, posted), comment_id=101)
        args.receipt = args.output
        for command in ("verify", "verify-ack", "verify-ack"):
            args.command = command
            with (
                patch.object(probe, "github_read", side_effect=[current, [posted, ack]]) as read,
                patch.object(bridge, "datetime", wraps=datetime) as clock,
            ):
                clock.now.return_value = NOW + timedelta(seconds=3)
                assert bridge.run(args) == 0
                assert read.call_args_list[0].args == (32,)
                assert read.call_args_list[1].kwargs == {"comments": True}
        gh.assert_not_called()
