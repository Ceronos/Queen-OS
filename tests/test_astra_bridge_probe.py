"""Network-free admission and receipt tests for the Astra one-shot probe bridge."""

import importlib.util
import json
import sys
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
        with patch.object(bridge.platform, "system", return_value="Linux"), patch.object(
            bridge.platform, "machine", return_value="x86_64"
        ):
            text = bridge.make_receipt(request, NOW, gpu={"status": "unavailable"})
        obj = json.loads(text.split("\n", 1)[1])
        import hashlib

        self.assertEqual(obj["result_sha256"], hashlib.sha256(bridge.canonical(obj["result"]).encode()).hexdigest())
        self.assertEqual(obj["attestation"], "none; producer self-report only")
        self.assertEqual(obj["result"]["os"], "Linux")

    def test_repo_cannot_redirect_github_lookups(self):
        with self.assertRaises(ValueError):
            bridge.github_issues("evil.com/repo?redirect=https://x")

    def test_no_command_execution_during_dry_run(self):
        with (
            patch.object(bridge, "github_issues", return_value=[valid_issue()]),
            patch.object(bridge, "post_comment") as post,
            patch.object(bridge, "make_receipt", return_value="RECEIPT"),
            patch.object(bridge, "load_processed", return_value=set()),
        ):
            self.assertEqual(bridge.run(post=False, state=Path("unused")), 0)
        post.assert_not_called()


if __name__ == "__main__":
    unittest.main()
