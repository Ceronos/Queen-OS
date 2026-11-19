"""Controlled offline lifecycle receipts: no providers, network, credentials or real malware."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from scripts.test_observer import MAX_EVENT_BYTES, Recorder, _event, audit, main

ROOT = Path(__file__).resolve().parents[1]


def test_reconciles_clean_run(tmp_path: Path) -> None:
    path = tmp_path / "events.jsonl"
    writer = Recorder(path)
    writer.start()
    writer.test_start("tests/test_example.py::test_one[private-parameter]")
    test_id, _ = writer.identity("tests/test_example.py::test_one[private-parameter]")
    writer.append(_event("test_phase", test_id=test_id, phase="call", outcome="passed", duration_ms=3))
    writer.append(_event("test_end", test_id=test_id))
    writer.active.remove(test_id)
    writer.finish(0)
    assert "private-parameter" not in path.read_text()
    assert audit(path)["status"] == "CLOSED_PASS"
    assert audit(path)["session_closed"] is True


def test_missing_teardown_never_closes_successfully(tmp_path: Path) -> None:
    path = tmp_path / "events.jsonl"
    writer = Recorder(path)
    writer.start()
    writer.test_start("tests/test_example.py::test_one")
    assert audit(path)["status"] == "UNCLOSED_OR_FAIL"
    assert audit(path)["unfinished"] == 1
    writer.finish(0)
    assert audit(path)["status"] == "UNCLOSED_OR_FAIL"


def test_failed_pytest_exit_is_not_a_pass(tmp_path: Path) -> None:
    path = tmp_path / "events.jsonl"
    writer = Recorder(path)
    writer.start()
    writer.finish(1)
    report = audit(path)
    assert report["status"] == "UNCLOSED_OR_FAIL" and report["pytest_exitstatus"] == 1


def test_missing_truncated_duplicate_and_invalid_evidence(tmp_path: Path) -> None:
    path = tmp_path / "events.jsonl"
    assert audit(path)["status"] == "UNOBSERVED"
    path.write_text('{"v":1,"event":"session_start"')
    assert audit(path)["status"] == "INVALID_EVIDENCE"
    writer = Recorder(path)
    path.unlink()
    writer.start()
    writer.start()
    assert audit(path)["status"] == "INVALID_EVIDENCE"
    path.write_text("X" * MAX_EVENT_BYTES + "\n")
    assert audit(path)["status"] == "INVALID_EVIDENCE"


def test_symlink_refused(tmp_path: Path) -> None:
    target = tmp_path / "target.jsonl"
    target.write_text("untouched")
    link = tmp_path / "link"
    try:
        link.symlink_to(target)
    except OSError:
        return
    assert audit(link)["status"] == "UNOBSERVED"
    writer = Recorder(link)
    try:
        writer.start()
    except OSError:
        pass
    else:
        raise AssertionError("symlink target was modified")
    assert target.read_text() == "untouched"


def test_summary_emits_status_and_nonzero_for_unobserved(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("GITHUB_STEP_SUMMARY", raising=False)
    out = tmp_path / "report.json"
    assert main(["summarize", "--input", str(tmp_path / "missing"), "--output", str(out)]) == 2
    assert json.loads(out.read_text())["status"] == "UNOBSERVED"


def test_pytest_plugin_lifecycle_in_subprocess(tmp_path: Path) -> None:
    test_file = tmp_path / "test_example.py"
    test_file.write_text("def test_pass():\n    assert True\n")
    receipt = tmp_path / "events.jsonl"
    env = dict(os.environ, QUEEN_TEST_TELEMETRY_PATH=str(receipt), QUEEN_TEST_SELECTION="fixture")
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "-p", "scripts.test_observer", "-q", str(test_file)],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert proc.returncode == 0, proc.stdout[-1000:] + proc.stderr[-1000:]
    report = audit(receipt)
    assert report["status"] == "CLOSED_PASS"
    assert report["started"] == report["ended"] == 1


def test_ci_wiring_is_always_audited() -> None:
    for workflow in ["ci.yml", "live-canary.yml"]:
        text = (ROOT / ".github/workflows" / workflow).read_text()
        assert "-p scripts.test_observer" in text
        assert "QUEEN_TEST_TELEMETRY_PATH:" in text
        assert "if: always()" in text
        assert "test_observer.py summarize" in text
        assert "test-lifecycle-" in text
