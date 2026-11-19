#!/usr/bin/env python3
"""Opt-in, metadata-only pytest lifecycle evidence for Queen-OS CI.

The observer is deliberately not a security sandbox or independent witness.
No environment dump, test parameter values, logs, traceback, payload, or secrets
are recorded. A missing close is UNKNOWN/UNCLOSED, never inferred as success.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

import pytest

MAX_EVENT_BYTES = 4096
MAX_LOG_BYTES = 16 * 1024 * 1024
SCHEMA = 1


def _event(kind: str, **values: Any) -> dict[str, Any]:
    return {"v": SCHEMA, "event": kind, "utc_ms": int(time.time() * 1000), **values}


class Recorder:
    def __init__(self, path: Path):
        self.path = path
        self.active: set[str] = set()

    def append(self, event: dict[str, Any]) -> None:
        encoded = (json.dumps(event, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode()
        if len(encoded) > MAX_EVENT_BYTES:
            raise ValueError("test event exceeds bound")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if self.path.is_symlink():
            raise OSError("refuse symlinked telemetry path")
        flags = os.O_WRONLY | os.O_CREAT | os.O_APPEND
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        fd = os.open(self.path, flags, 0o600)
        try:
            if os.fstat(fd).st_size + len(encoded) > MAX_LOG_BYTES:
                raise ValueError("test event log exceeds bound")
            if os.write(fd, encoded) != len(encoded):
                raise OSError("short test event write")
            os.fsync(fd)
        finally:
            os.close(fd)

    def start(self) -> None:
        # Allowlist of execution metadata; never record arbitrary environment values.
        self.append(
            _event(
                "session_start",
                run_id=os.environ.get("GITHUB_RUN_ID", "local")[:64],
                run_attempt=os.environ.get("GITHUB_RUN_ATTEMPT", "local")[:16],
                workflow=os.environ.get("GITHUB_WORKFLOW", "local")[:128],
                commit=os.environ.get("GITHUB_SHA", "local")[:64],
                runner_os=sys.platform,
                python=f"{sys.version_info.major}.{sys.version_info.minor}",
                selection=os.environ.get("QUEEN_TEST_SELECTION", "unspecified")[:32],
            )
        )

    @staticmethod
    def identity(nodeid: str) -> tuple[str, str]:
        # Parameter values in node IDs may be sensitive. Use a digest, never raw IDs.
        return hashlib.sha256(nodeid.encode()).hexdigest(), nodeid.split("[", 1)[0][:240]

    def test_start(self, nodeid: str) -> None:
        test_id, test_name = self.identity(nodeid)
        if test_id in self.active:
            raise ValueError("test started twice without observed teardown")
        self.active.add(test_id)
        self.append(_event("test_start", test_id=test_id, test=test_name))

    def test_phase(self, report: pytest.TestReport) -> None:
        test_id, _ = self.identity(report.nodeid)
        if test_id not in self.active:
            raise ValueError("phase report without observed test start")
        self.append(
            _event(
                "test_phase",
                test_id=test_id,
                phase=report.when,
                outcome=report.outcome,
                duration_ms=round(max(0.0, report.duration) * 1000),
            )
        )
        if report.when == "teardown":
            self.append(_event("test_end", test_id=test_id))
            self.active.remove(test_id)

    def finish(self, exitstatus: int) -> None:
        self.append(_event("session_end", exitstatus=int(exitstatus), open_tests=len(self.active)))


_RECORDER: Recorder | None = None


def pytest_configure(config: pytest.Config) -> None:
    global _RECORDER
    path = os.environ.get("QUEEN_TEST_TELEMETRY_PATH")
    _RECORDER = Recorder(Path(path)) if path else None


def pytest_sessionstart(session: pytest.Session) -> None:
    if _RECORDER is not None:
        _RECORDER.start()


def pytest_runtest_logstart(nodeid: str, location: tuple[str, int | None, str]) -> None:
    if _RECORDER is not None:
        _RECORDER.test_start(nodeid)


def pytest_runtest_logreport(report: pytest.TestReport) -> None:
    if _RECORDER is not None:
        _RECORDER.test_phase(report)


def pytest_sessionfinish(session: pytest.Session, exitstatus: int | pytest.ExitCode) -> None:
    if _RECORDER is not None:
        _RECORDER.finish(int(exitstatus))


def audit(path: Path) -> dict[str, Any]:
    summary: dict[str, Any] = {
        "v": SCHEMA,
        "status": "UNOBSERVED",
        "session_closed": False,
        "started": 0,
        "ended": 0,
        "unfinished": 0,
        "failed_phases": 0,
        "skipped_phases": 0,
        "pytest_exitstatus": None,
    }
    try:
        if path.is_symlink() or not path.is_file() or path.stat().st_size > MAX_LOG_BYTES:
            return summary
        active: set[str] = set()
        seen: set[str] = set()
        began = False
        closed = False
        with path.open("rb") as stream:
            for raw in stream:
                if not raw.endswith(b"\n") or len(raw) > MAX_EVENT_BYTES:
                    raise ValueError("truncated or oversized record")
                obj = json.loads(raw)
                if (
                    not isinstance(obj, dict)
                    or type(obj.get("v")) is not int
                    or obj["v"] != SCHEMA
                    or type(obj.get("utc_ms")) is not int
                ):
                    raise ValueError("invalid event schema")
                kind = obj.get("event")
                if closed or (not began and kind != "session_start"):
                    raise ValueError("out of order session event")
                if kind == "session_start":
                    if began:
                        raise ValueError("duplicate session start")
                    began = True
                elif kind == "test_start":
                    test_id = obj.get("test_id")
                    if not isinstance(test_id, str) or len(test_id) != 64 or test_id in seen:
                        raise ValueError("duplicate or invalid test identity")
                    active.add(test_id)
                    seen.add(test_id)
                    summary["started"] += 1
                elif kind == "test_phase":
                    if (
                        obj.get("test_id") not in active
                        or obj.get("phase") not in {"setup", "call", "teardown"}
                        or obj.get("outcome") not in {"passed", "failed", "skipped"}
                    ):
                        raise ValueError("invalid phase")
                    summary["failed_phases"] += obj["outcome"] == "failed"
                    summary["skipped_phases"] += obj["outcome"] == "skipped"
                elif kind == "test_end":
                    test_id = obj.get("test_id")
                    if test_id not in active:
                        raise ValueError("close without start")
                    active.remove(test_id)
                    summary["ended"] += 1
                elif kind == "session_end":
                    code = obj.get("exitstatus")
                    if type(code) is not int or type(obj.get("open_tests")) is not int:
                        raise ValueError("invalid session close")
                    if obj["open_tests"] != len(active):
                        raise ValueError("open-test count mismatch")
                    summary["pytest_exitstatus"] = code
                    closed = True
                else:
                    raise ValueError("unrecognized event")
        summary["unfinished"] = len(active)
        summary["session_closed"] = closed
        if began:
            success = closed and not active and summary["pytest_exitstatus"] == 0
            summary["status"] = "CLOSED_PASS" if success else "UNCLOSED_OR_FAIL"
    except (OSError, ValueError, UnicodeError, TypeError):
        summary["status"] = "INVALID_EVIDENCE"
        summary["session_closed"] = False
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Audit bounded, metadata-only pytest lifecycle receipts")
    sub = parser.add_subparsers(dest="command", required=True)
    cmd = sub.add_parser("summarize")
    cmd.add_argument("--input", required=True, type=Path)
    cmd.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)
    report = audit(args.input)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    result = (
        f"Test lifecycle: {report['status']} "
        f"(started={report['started']}, ended={report['ended']}, unfinished={report['unfinished']})"
    )
    print(result)
    if summary_file := os.environ.get("GITHUB_STEP_SUMMARY"):
        with Path(summary_file).open("a", encoding="utf-8") as stream:
            stream.write(f"\n### Test lifecycle\n\n{result}\n")
    return 0 if report["status"] == "CLOSED_PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
