"""Network-free admission and receipt tests for the Astra one-shot probe bridge."""

import hashlib
import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import patch

MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts/astra_bridge_probe.py"
SPEC = importlib.util.spec_from_file_location("astra_bridge_probe", MODULE_PATH)
assert SPEC and SPEC.loader
bridge = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = bridge
SPEC.loader.exec_module(bridge)

NOW = datetime(2026, 11, 16, 18, 0, tzinfo=UTC)


def valid_issue():
    data = {
        "protocol": bridge.PROTOCOL,
        "request_id": "astra-001",
        "kind": "probe",
        "expires_at": (NOW + timedelta(days=3)).isoformat().replace("+00:00", "Z"),
    }
    return {
        "number": 31,
        "state": "open",
        "title": bridge.TITLE,
        "user": {"login": "Ceronos"},
        "body": bridge.MARKER + "\n" + json.dumps(data),
    }


class AdmissionTests(unittest.TestCase):
    def test_admit_authorized_request(self):
        self.assertEqual(bridge.validate_request(valid_issue(), NOW), {"request_id": "astra-001", "issue_number": "31"})

    def test_wrong_author_refused(self):
        issue = valid_issue()
        issue["user"]["login"] = "random-stranger"
        self.assertIsNone(bridge.validate_request(issue, NOW))

    def test_pull_request_refused(self):
        issue = valid_issue()
        issue["pull_request"] = {}
        self.assertIsNone(bridge.validate_request(issue, NOW))

    def test_closed_or_missing_author_refused(self):
        for fields in ({"state": "closed"}, {"user": None}):
            with self.subTest(fields=fields):
                self.assertIsNone(bridge.validate_request(valid_issue() | fields, NOW))

    def test_duplicate_json_field_refused(self):
        issue = valid_issue()
        issue["body"] = issue["body"].replace('"kind": "probe"', '"kind": "run_shell", "kind": "probe"')
        self.assertIsNone(bridge.validate_request(issue, NOW))

    def test_expired_request_refused(self):
        issue = valid_issue()
        data = json.loads(issue["body"].split("\n", 1)[1])
        data["expires_at"] = (NOW - timedelta(seconds=1)).isoformat().replace("+00:00", "Z")
        issue["body"] = bridge.MARKER + "\n" + json.dumps(data)
        self.assertIsNone(bridge.validate_request(issue, NOW))

    def test_unbounded_future_refused(self):
        issue = valid_issue()
        data = json.loads(issue["body"].split("\n", 1)[1])
        data["expires_at"] = (NOW + timedelta(days=8)).isoformat().replace("+00:00", "Z")
        issue["body"] = bridge.MARKER + "\n" + json.dumps(data)
        self.assertIsNone(bridge.validate_request(issue, NOW))

    def test_unknown_kind_refused(self):
        issue = valid_issue()
        data = json.loads(issue["body"].split("\n", 1)[1])
        data["kind"] = "run_shell"
        issue["body"] = bridge.MARKER + "\n" + json.dumps(data)
        self.assertIsNone(bridge.validate_request(issue, NOW))

    def test_extra_parameters_refused(self):
        issue = valid_issue()
        data = json.loads(issue["body"].split("\n", 1)[1])
        data["command"] = "ls"
        issue["body"] = bridge.MARKER + "\n" + json.dumps(data)
        self.assertIsNone(bridge.validate_request(issue, NOW))

    def test_invalid_id_refused(self):
        issue = valid_issue()
        data = json.loads(issue["body"].split("\n", 1)[1])
        data["request_id"] = "../escape"
        issue["body"] = bridge.MARKER + "\n" + json.dumps(data)
        self.assertIsNone(bridge.validate_request(issue, NOW))

    def test_marker_required(self):
        issue = valid_issue()
        issue["body"] = issue["body"].replace(bridge.MARKER, "DO-ANYTHING", 1)
        self.assertIsNone(bridge.validate_request(issue, NOW))

    def test_receipt_hash_is_rederivable(self):
        request = bridge.validate_request(valid_issue(), NOW)
        with (
            patch.object(bridge.platform, "system", return_value="Linux"),
            patch.object(bridge.platform, "machine", return_value="x86_64"),
        ):
            text = bridge.make_receipt(request, NOW, gpu={"status": "unavailable"})
        obj = json.loads(text.split("\n", 1)[1])
        self.assertEqual(obj["result_sha256"], hashlib.sha256(bridge.canonical(obj["result"]).encode()).hexdigest())
        self.assertEqual(obj["attestation"], "none; producer self-report only")
        self.assertEqual(obj["result"]["os"], "Linux")

    def test_repo_cannot_redirect_github_lookups(self):
        with self.assertRaises(ValueError):
            bridge.github_read("evil.com/repo?redirect=https://x")
        self.assertIsNone(bridge.NoRedirect().redirect_request(None, None, 302, "", {}, "https://example.com"))

    def test_dry_run_reads_only_the_selected_issue_and_uses_no_gh(self):
        issue = valid_issue()
        expires = (datetime.now(UTC) + timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
        issue["body"] = issue["body"].replace("2026-11-19T18:00:00Z", expires)
        with (
            patch.object(bridge, "github_read", return_value=issue) as read,
            patch.object(bridge, "github_cli") as gh,
            patch.object(bridge, "make_receipt", return_value="RECEIPT"),
            tempfile.TemporaryDirectory() as directory,
        ):
            state = Path(directory) / "state.json"
            self.assertEqual(bridge.run(issue_number=31, request_id="astra-001", post=False, state=state), 0)
            self.assertFalse(state.exists())
        read.assert_called_once_with(31)
        gh.assert_not_called()

    def test_wrong_issue_or_id_refused_before_probe(self):
        with (
            patch.object(bridge, "github_read", return_value=valid_issue()),
            patch.object(bridge, "datetime", wraps=datetime) as clock,
            patch.object(bridge, "make_receipt") as probe,
        ):
            clock.now.return_value = NOW
            self.assertEqual(bridge.run(issue_number=32, request_id="astra-001", post=False, state=Path("unused")), 2)
            self.assertEqual(bridge.run(issue_number=31, request_id="other", post=False, state=Path("unused")), 2)
        probe.assert_not_called()

    def test_acknowledgment_loss_recovers_from_same_author_receipt(self):
        issue = valid_issue()
        receipt = bridge.make_receipt({"issue_number": "31", "request_id": "astra-001"}, NOW, {"status": "unavailable"})
        comments = [{"user": {"login": "astra-producer"}, "body": receipt}]
        with (
            tempfile.TemporaryDirectory() as directory,
            patch.object(bridge, "github_read", side_effect=[issue, [], issue, issue, comments]),
            patch.object(bridge, "datetime", wraps=datetime) as clock,
            patch.object(
                bridge,
                "github_cli",
                side_effect=["astra-producer", subprocess.TimeoutExpired("gh", 20), "astra-producer"],
            ) as gh,
            patch.object(bridge, "make_receipt", return_value=receipt),
        ):
            clock.now.return_value = NOW
            state = Path(directory) / "state.json"
            with self.assertRaises(subprocess.TimeoutExpired):
                bridge.run(issue_number=31, request_id="astra-001", post=True, state=state)
            self.assertFalse(state.exists())
            self.assertEqual(bridge.run(issue_number=31, request_id="astra-001", post=True, state=state), 0)
            self.assertEqual(bridge.load_processed(state), {"31:astra-001"})
            self.assertFalse(state.with_name("state.json.lock").exists())
        self.assertEqual(sum("--method" in call.args for call in gh.call_args_list), 1)


if __name__ == "__main__":
    unittest.main()
