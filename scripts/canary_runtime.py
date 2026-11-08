#!/usr/bin/env python3
"""Pinned canary-runtime acquisition and phase reporting; no installation or inference."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import tempfile
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

MAX_ATTEMPTS = 3
BACKOFF_SECONDS = (5, 15)
TRANSIENT_HTTP = {408, 429, 500, 502, 503, 504}
TRANSIENT_CURL = {5, 6, 7, 18, 28, 52, 56}


class AcquisitionError(ValueError):
    """No verified archive is available. Phase evidence is retained separately."""


@dataclass(frozen=True)
class RuntimePin:
    version: str
    platform: str
    asset: str
    url: str
    bytes: int
    sha256: str


@dataclass(frozen=True)
class Transfer:
    exit_code: int
    http_status: int


def _pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in items:
        if key in result:
            raise AcquisitionError("duplicate pin field")
        result[key] = value
    return result


def load_pin(path: Path, expected_version: str) -> RuntimePin:
    with path.open("rb") as stream:
        raw = stream.read(8193)
    if len(raw) > 8192:
        raise AcquisitionError("pin record exceeds bound")
    value = json.loads(raw.decode("utf-8"), object_pairs_hook=_pairs)
    if (
        not isinstance(value, dict)
        or set(value) != {"v", "version", "platform", "asset", "url", "bytes", "sha256"}
        or type(value["v"]) is not int
        or value["v"] != 1
        or value["version"] != expected_version
        or not isinstance(value["version"], str)
        or re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", value["version"]) is None
        or value["platform"] != "linux-amd64"
        or value["asset"] != "ollama-linux-amd64.tar.zst"
        or value["url"] != f"https://github.com/ollama/ollama/releases/download/v{expected_version}/{value['asset']}"
        or type(value["bytes"]) is not int
        or not 1 <= value["bytes"] <= 2 * 1024**3
        or not isinstance(value["sha256"], str)
        or re.fullmatch(r"[0-9a-f]{64}", value["sha256"]) is None
    ):
        raise AcquisitionError("invalid or mismatched committed runtime pin")
    return RuntimePin(**{k: v for k, v in value.items() if k != "v"})


def _record(path: Path, value: dict[str, Any]) -> None:
    if path.is_symlink():
        raise AcquisitionError("refuse symlinked acquisition receipt")
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=".acquisition-", dir=path.parent)
    temporary = Path(name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as stream:
            json.dump(value, stream, indent=2, sort_keys=True, allow_nan=False)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def _info(path: Path, limit: int) -> tuple[int, str | None]:
    if path.is_symlink():
        raise AcquisitionError("refuse symlinked runtime archive")
    if not path.is_file():
        raise AcquisitionError("runtime archive must be a regular file")
    if path.stat().st_size > limit:
        return path.stat().st_size, None
    digest, size = hashlib.sha256(), 0
    with path.open("rb") as stream:
        while chunk := stream.read(min(1024 * 1024, limit + 1 - size)):
            digest.update(chunk)
            size += len(chunk)
            if size > limit:
                return size, None
    return size, digest.hexdigest()


def download(pin: RuntimePin, partial: Path) -> Transfer:
    # Fixed public HTTPS asset; ignore user curl config. No shell, auth, installer or inference.
    command = [
        "curl",
        "--disable",
        "--fail",
        "--location",
        "--silent",
        "--show-error",
        "--proto",
        "=https",
        "--proto-redir",
        "=https",
        "--connect-timeout",
        "15",
        "--max-time",
        "120",
        "--max-filesize",
        str(pin.bytes),
        "--output",
        str(partial),
        "--write-out",
        "%{http_code}",
        pin.url,
    ]
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=135, check=False)  # noqa: S603
    except subprocess.TimeoutExpired:
        return Transfer(28, 0)
    except FileNotFoundError:
        return Transfer(127, 0)
    status = result.stdout.strip()
    return Transfer(result.returncode, int(status) if re.fullmatch(r"[0-9]{3}", status) else 0)


def acquire(
    pin: RuntimePin,
    archive: Path,
    receipt: Path,
    *,
    transfer: Callable[[RuntimePin, Path], Transfer] = download,
    sleep: Callable[[float], None] = time.sleep,
    fixture: bool = False,
) -> dict[str, Any]:
    """Retry only byte acquisition. Verification is mandatory before the archive is published."""
    if archive.resolve() == receipt.resolve():
        raise AcquisitionError("archive and receipt must be different paths")
    report: dict[str, Any] = {
        "v": 1,
        "kind": "canary.runtime_acquisition",
        "fixture": fixture,
        "pin": asdict(pin),
        "status": "IN_PROGRESS",
        "attempts": [],
        "inference_requests": 0,
    }
    _record(receipt, report)
    archive.parent.mkdir(parents=True, exist_ok=True)
    if archive.exists() or archive.is_symlink():
        try:
            size, digest = _info(archive, pin.bytes)
        except (AcquisitionError, OSError) as exc:
            report["status"] = "EXISTING_ARCHIVE_REFUSED"
            _record(receipt, report)
            raise AcquisitionError(report["status"]) from exc
        if (size, digest) != (pin.bytes, pin.sha256):
            report["status"] = "EXISTING_ARCHIVE_REFUSED"
            _record(receipt, report)
            raise AcquisitionError(report["status"])
        report["status"] = "PINNED_RUNTIME_ARCHIVE_VERIFIED"
        report["source"] = "existing_verified_file"
        _record(receipt, report)
        return report
    with tempfile.TemporaryDirectory(prefix=".runtime-download-", dir=archive.parent) as folder:
        partial = Path(folder) / "archive.part"
        for attempt in range(1, MAX_ATTEMPTS + 1):
            report["status"] = "IN_PROGRESS"
            entry: dict[str, Any] = {"attempt": attempt, "status": "IN_PROGRESS"}
            report["attempts"].append(entry)
            _record(receipt, report)
            partial.touch(exist_ok=False)
            try:
                result = transfer(pin, partial)
                try:
                    size, digest = _info(partial, pin.bytes)
                except AcquisitionError as exc:
                    entry["status"] = "ARCHIVE_READBACK_REFUSED"
                    report["status"] = "ARCHIVE_READBACK_REFUSED"
                    _record(receipt, report)
                    raise AcquisitionError("ARCHIVE_READBACK_REFUSED") from exc
                entry.update(
                    {
                        "curl_exit": result.exit_code,
                        "http_status": result.http_status,
                        "received_bytes": size,
                        "received_sha256": digest,
                    }
                )
                if size > pin.bytes:
                    status, retry = "SIZE_LIMIT_EXCEEDED", False
                elif result.exit_code == 0 and result.http_status == 200 and size == pin.bytes:
                    status, retry = ("VERIFIED", False) if digest == pin.sha256 else ("DIGEST_MISMATCH", False)
                elif result.exit_code == 0 and result.http_status == 200:
                    status, retry = "INCOMPLETE_RESPONSE", True
                else:
                    retry = result.http_status in TRANSIENT_HTTP or (
                        result.http_status in {0, 200} and result.exit_code in TRANSIENT_CURL
                    )
                    status = "TRANSIENT_DOWNLOAD_ERROR" if retry else "DOWNLOAD_REFUSED"
                entry["status"] = status
                if status == "VERIFIED":
                    with partial.open("rb+") as stream:
                        os.fsync(stream.fileno())
                    partial.replace(archive)
                    report["status"] = "PINNED_RUNTIME_ARCHIVE_VERIFIED"
                    report["source"] = "download"
                    _record(receipt, report)
                    return report
                report["status"] = (
                    "RETRY_PENDING"
                    if retry and attempt < MAX_ATTEMPTS
                    else ("DOWNLOAD_RETRIES_EXHAUSTED" if retry else status)
                )
                _record(receipt, report)
                if not retry or attempt == MAX_ATTEMPTS:
                    raise AcquisitionError(report["status"])
            except OSError as exc:
                entry.update({"status": "LOCAL_IO_ERROR", "error_type": type(exc).__name__})
                report["status"] = "LOCAL_IO_ERROR"
                _record(receipt, report)
                raise AcquisitionError("LOCAL_IO_ERROR") from exc
            finally:
                if partial.is_dir() and not partial.is_symlink():
                    partial.rmdir()
                else:
                    partial.unlink(missing_ok=True)
            sleep(BACKOFF_SECONDS[attempt - 1])
    raise AcquisitionError("unreachable acquisition state")


PHASES = (
    ("ACQUISITION", "Pinned runtime archive"),
    ("RUNTIME", "Runtime extraction/version/readiness"),
    ("MODEL", "Model acquisition"),
    ("PYTEST", "Witnessed pytest inference"),
    ("CLI", "CLI receipt/ledger and archive integrity"),
    ("ANSWER", "Strict CLI answer oracle"),
)


def phase_summary(outcomes: dict[str, str]) -> str:
    allowed = {"success", "failure", "cancelled", "skipped"}
    lines = ["## Keyless canary phases", "", "| Phase | Outcome |", "| --- | --- |"]
    for key, label in PHASES:
        outcome = outcomes.get(key) or "not_run"
        if outcome not in allowed | {"not_run"}:
            raise AcquisitionError("unknown phase outcome")
        lines.append(f"| {label} | {outcome} |")
    lines.extend(
        [
            "",
            "Archive integrity and the strict answer oracle are separate results.",
            "Download retries do not retry inference. Failed/skipped phases are not passes.",
            "",
        ]
    )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="operation", required=True)
    fetch = sub.add_parser("acquire")
    fetch.add_argument("--pin", type=Path, required=True)
    fetch.add_argument("--expected-version", required=True)
    fetch.add_argument("--archive", type=Path, required=True)
    fetch.add_argument("--receipt", type=Path, required=True)
    sub.add_parser("summary")
    args = parser.parse_args(argv)
    try:
        if args.operation == "summary":
            text = phase_summary({key: os.environ.get("CANARY_PHASE_" + key, "") for key, _ in PHASES})
            with Path(os.environ["GITHUB_STEP_SUMMARY"]).open("a", encoding="utf-8") as stream:
                stream.write(text)
            print(text)
        else:
            pin = load_pin(args.pin, args.expected_version)
            result = acquire(pin, args.archive, args.receipt)
            print(json.dumps({"status": result["status"], "attempts": len(result["attempts"])}))
    except (AcquisitionError, OSError, ValueError, KeyError) as exc:
        print(
            json.dumps(
                {"phase": "runtime_acquisition_or_summary", "status": "FAILED", "error_type": type(exc).__name__}
            )
        )
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
