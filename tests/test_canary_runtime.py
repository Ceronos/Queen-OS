"""Offline runtime-acquisition faults; no network, runtime installation or inference."""

from __future__ import annotations

import hashlib
import json
import runpy
import subprocess
from dataclasses import asdict
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = runpy.run_path(str(ROOT / "scripts/canary_runtime.py"))
RuntimePin = SCRIPT["RuntimePin"]
Transfer = SCRIPT["Transfer"]
AcquisitionError = SCRIPT["AcquisitionError"]
acquire = SCRIPT["acquire"]
load_pin = SCRIPT["load_pin"]
DATA = b"synthetic archive bytes, not a runtime"


def pin():
    return RuntimePin(
        "0.40.15",
        "linux-amd64",
        "ollama-linux-amd64.tar.zst",
        "https://github.com/ollama/ollama/releases/download/v0.40.15/ollama-linux-amd64.tar.zst",
        len(DATA),
        hashlib.sha256(DATA).hexdigest(),
    )


def run_attempts(tmp_path, replies):
    archive, receipt = tmp_path / "runtime.zst", tmp_path / "receipt.json"
    calls, sleeps = [], []

    def transfer(_, partial):
        assert not archive.exists()  # Nothing is accepted before exact byte verification.
        before = json.loads(receipt.read_text())
        assert before["status"] == "IN_PROGRESS"
        assert before["attempts"][-1]["status"] == "IN_PROGRESS"
        assert partial.read_bytes() == b""  # Retry never appends to prior failed bytes.
        calls.append(partial)
        data, code, http = replies[len(calls) - 1]
        partial.write_bytes(data)
        return Transfer(code, http)

    return archive, receipt, calls, sleeps, transfer


@pytest.mark.parametrize("first", [(b"", 22, 504), (DATA[:4], 18, 200), (DATA[:4], 0, 200), (b"", 28, 0)])
def test_transient_download_then_complete_bytes(first, tmp_path):
    archive, receipt, calls, sleeps, transfer = run_attempts(tmp_path, [first, (DATA, 0, 200)])
    report = acquire(pin(), archive, receipt, transfer=transfer, sleep=sleeps.append, fixture=True)
    assert archive.read_bytes() == DATA
    assert report == json.loads(receipt.read_text())
    assert report["fixture"] is True and report["inference_requests"] == 0
    assert report["status"] == "PINNED_RUNTIME_ARCHIVE_VERIFIED"
    assert report["attempts"][0]["received_bytes"] == len(first[0])
    assert report["attempts"][1]["status"] == "VERIFIED"
    assert len(calls) == 2 and sleeps == [5]
    assert all(not path.exists() for path in calls)
    assert not list(tmp_path.glob(".runtime-download-*"))


def test_exhaustion_retains_all_attempts_and_never_publishes(tmp_path):
    archive, receipt, calls, sleeps, transfer = run_attempts(tmp_path, [(DATA[:2], 18, 200)] * 3)
    with pytest.raises(AcquisitionError, match="DOWNLOAD_RETRIES_EXHAUSTED"):
        acquire(pin(), archive, receipt, transfer=transfer, sleep=sleeps.append, fixture=True)
    report = json.loads(receipt.read_text())
    assert report["status"] == "DOWNLOAD_RETRIES_EXHAUSTED"
    assert len(report["attempts"]) == len(calls) == 3
    assert sleeps == [5, 15] and not archive.exists()
    assert all(x["received_bytes"] == 2 for x in report["attempts"])
    assert not list(tmp_path.glob(".runtime-download-*"))


@pytest.mark.parametrize(
    "reply,status",
    [
        ((b"x" * len(DATA), 0, 200), "DIGEST_MISMATCH"),
        ((DATA + b"extra", 0, 200), "SIZE_LIMIT_EXCEEDED"),
        ((b"", 22, 404), "DOWNLOAD_REFUSED"),
        ((b"", 60, 0), "DOWNLOAD_REFUSED"),
        ((DATA, 0, 0), "DOWNLOAD_REFUSED"),
    ],
)
def test_integrity_permanent_and_certificate_failures_are_terminal(reply, status, tmp_path):
    archive, receipt, calls, sleeps, transfer = run_attempts(tmp_path, [reply])
    with pytest.raises(AcquisitionError, match=status):
        acquire(pin(), archive, receipt, transfer=transfer, sleep=sleeps.append, fixture=True)
    report = json.loads(receipt.read_text())
    assert report["status"] == status and report["attempts"][0]["status"] == status
    assert len(calls) == 1 and sleeps == [] and not archive.exists()
    if status == "SIZE_LIMIT_EXCEEDED":
        assert report["attempts"][0]["received_sha256"] is None  # Never mislabel a partial digest.


def test_existing_verified_bytes_reused_without_network(tmp_path):
    archive, receipt = tmp_path / "archive", tmp_path / "receipt.json"
    archive.write_bytes(DATA)
    result = acquire(pin(), archive, receipt, transfer=lambda *_: pytest.fail("network"), fixture=True)
    assert result["source"] == "existing_verified_file" and result["attempts"] == []


def test_existing_wrong_bytes_preserved_without_network(tmp_path):
    archive, receipt = tmp_path / "archive", tmp_path / "receipt.json"
    archive.write_bytes(b"prior unknown bytes")
    with pytest.raises(AcquisitionError, match="EXISTING_ARCHIVE_REFUSED"):
        acquire(pin(), archive, receipt, transfer=lambda *_: pytest.fail("network"), fixture=True)
    assert archive.read_bytes() == b"prior unknown bytes"
    assert json.loads(receipt.read_text())["status"] == "EXISTING_ARCHIVE_REFUSED"


def symlink_or_skip(link, target):
    try:
        link.symlink_to(target)
    except OSError as exc:
        pytest.skip(f"host does not permit symlinks: {type(exc).__name__}")


def test_existing_symlink_refused(tmp_path):
    target = tmp_path / "target"
    target.write_bytes(DATA)
    archive, receipt = tmp_path / "archive", tmp_path / "receipt.json"
    symlink_or_skip(archive, target)
    with pytest.raises(AcquisitionError, match="EXISTING_ARCHIVE_REFUSED"):
        acquire(pin(), archive, receipt, transfer=lambda *_: pytest.fail("network"), fixture=True)
    assert target.read_bytes() == DATA and archive.is_symlink()


@pytest.mark.parametrize("fault", ["remove", "directory", "symlink", "io"])
def test_unreadable_transfer_effect_is_recorded_without_retry(fault, tmp_path):
    archive, receipt = tmp_path / "archive", tmp_path / "receipt.json"
    calls = []

    def transfer(_, partial):
        calls.append(1)
        if fault == "io":
            raise OSError("synthetic private error text must not be exported")
        partial.unlink()
        if fault == "directory":
            partial.mkdir()
        elif fault == "symlink":
            symlink_or_skip(partial, tmp_path / "missing")
        return Transfer(0, 200)

    with pytest.raises(AcquisitionError):
        acquire(pin(), archive, receipt, transfer=transfer, sleep=lambda _: pytest.fail("retry"), fixture=True)
    report = json.loads(receipt.read_text())
    assert report["status"] == ("LOCAL_IO_ERROR" if fault == "io" else "ARCHIVE_READBACK_REFUSED")
    assert "private error" not in receipt.read_text()
    assert calls == [1] and not archive.exists()


def test_receipt_must_be_writable_before_network_or_publication(tmp_path):
    receipt = tmp_path / "directory"
    receipt.mkdir()
    with pytest.raises(OSError):
        acquire(pin(), tmp_path / "archive", receipt, transfer=lambda *_: pytest.fail("network"), fixture=True)
    assert not (tmp_path / "archive").exists()


def test_receipt_symlink_and_path_collision_refused(tmp_path):
    target = tmp_path / "target"
    target.write_text("preserve")
    receipt = tmp_path / "receipt"
    symlink_or_skip(receipt, target)
    with pytest.raises(AcquisitionError):
        acquire(pin(), tmp_path / "archive", receipt, transfer=lambda *_: pytest.fail("network"), fixture=True)
    assert target.read_text() == "preserve"
    with pytest.raises(AcquisitionError):
        acquire(pin(), target, target, transfer=lambda *_: pytest.fail("network"), fixture=True)
    assert target.read_text() == "preserve"


@pytest.mark.parametrize(
    "field,value",
    [
        ("v", True),
        ("v", 2),
        ("bytes", True),
        ("bytes", 0),
        ("bytes", 2**31 + 1),
        ("version", "0.40.14"),
        ("version", ["0.40.15"]),
        ("platform", "linux-arm64"),
        ("asset", "install.sh"),
        ("sha256", "A" * 64),
        ("sha256", "ab"),
        ("url", "http://github.com/ollama/ollama/releases/download/v0.40.15/ollama-linux-amd64.tar.zst"),
        ("url", "https://other.example/runtime"),
        ("extra", "field"),
    ],
)
def test_invalid_pin_rejected_before_transport(field, value, tmp_path):
    value_dict = {"v": 1, **asdict(pin()), field: value}
    path = tmp_path / "pin.json"
    path.write_text(json.dumps(value_dict))
    with pytest.raises(AcquisitionError):
        load_pin(path, "0.40.15")


def test_pin_missing_duplicate_oversized_and_invalid_json(tmp_path):
    path = tmp_path / "pin.json"
    for raw in ['{"v":1,"v":1}', "{}", "[1]", " " * 8193, "not json"]:
        path.write_text(raw)
        with pytest.raises(ValueError):
            load_pin(path, "0.40.15")
    path.write_text(json.dumps({"v": 1, **asdict(pin())}))
    assert load_pin(path, "0.40.15") == pin()
    with pytest.raises(AcquisitionError):
        load_pin(path, "0.40.14")


@pytest.mark.parametrize("fault,expected", [("timeout", (28, 0)), ("missing", (127, 0)), ("bad_status", (0, 0))])
def test_download_process_failures_do_not_invent_http_success(fault, expected, monkeypatch, tmp_path):
    def fake_run(command, **kwargs):
        assert command[0:2] == ["curl", "--disable"]
        assert kwargs.get("shell", False) is False
        for flag in ("--proto", "--proto-redir"):
            assert command[command.index(flag) + 1] == "=https"
        assert kwargs["timeout"] == 135
        if fault == "timeout":
            raise subprocess.TimeoutExpired(command, 135)
        if fault == "missing":
            raise FileNotFoundError
        return SimpleNamespace(returncode=0, stdout="untrusted non-status response")

    monkeypatch.setattr(subprocess, "run", fake_run)
    result = SCRIPT["download"](pin(), tmp_path / "partial")
    assert (result.exit_code, result.http_status) == expected


def test_phase_summary_keeps_acquisition_integrity_and_answer_distinct():
    summary = SCRIPT["phase_summary"]({"ACQUISITION": "failure", "PYTEST": "skipped"})
    assert "| Pinned runtime archive | failure |" in summary
    assert "| Witnessed pytest inference | skipped |" in summary
    assert "| Strict CLI answer oracle | not_run |" in summary
    summary = SCRIPT["phase_summary"]({"CLI": "success", "ANSWER": "failure", "RUNTIME": "cancelled"})
    assert "| CLI receipt/ledger and archive integrity | success |" in summary
    assert "| Strict CLI answer oracle | failure |" in summary
    with pytest.raises(AcquisitionError):
        SCRIPT["phase_summary"]({"ANSWER": "unrecognized"})


def test_summary_cli_appends_without_using_model_name_as_phase(tmp_path, monkeypatch):
    path = tmp_path / "summary.md"
    path.write_text("prior summary\n")
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(path))
    monkeypatch.setenv("CANARY_MODEL", "qwen2.5:0.5b")
    monkeypatch.setenv("CANARY_PHASE_MODEL", "skipped")
    assert SCRIPT["main"](["summary"]) == 0
    assert path.read_text().startswith("prior summary\n")
    assert "| Model acquisition | skipped |" in path.read_text()


def test_workflow_failure_export_cannot_bypass_model_evidence_admission():
    workflow = (ROOT / ".github/workflows/live-canary.yml").read_text()
    active = "\n".join(line for line in workflow.splitlines() if not line.lstrip().startswith("#"))
    assert "pull_request:" not in active and "continue-on-error" not in active
    assert "secrets." not in workflow and "curl -fsSL https://ollama.com/install.sh" not in workflow
    assert workflow.count('queen infer ollama "$CANARY_MODEL"') == 1
    assert '--system "Return only the requested word."' in workflow and "--expect-word bee" in workflow
    always_export = workflow.split("- name: Retain runtime acquisition diagnostics", 1)[1]
    paths = [line.strip() for line in always_export.splitlines() if "${{ runner.temp }}/" in line]
    assert paths == [
        "${{ runner.temp }}/runtime-acquisition.json",
        "${{ runner.temp }}/ollama-version.txt",
        "${{ runner.temp }}/ollama-server-version.json",
    ]
    evidence_export = workflow.split("# Default success gating", 1)[1].split("- name: Require expected CLI answer", 1)[
        0
    ]
    assert "always()" not in evidence_export and "if-no-files-found: error" in evidence_export
