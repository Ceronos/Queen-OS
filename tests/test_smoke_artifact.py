"""Offline checks against preserved real-run evidence; no mock model execution."""

from __future__ import annotations

import hashlib
import io
import json
import os
import runpy
import shutil
import sqlite3
import stat
import subprocess
import sys
import warnings
import zipfile
from contextlib import closing
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/verify_smoke_artifact.py"
verify_archive = runpy.run_path(str(SCRIPT))["verify_archive"]
META = json.loads((ROOT / "tests/fixtures/canary-42373449340.json").read_text())


@pytest.fixture
def recorded_archive() -> Path:
    location = os.environ.get("QUEEN_ARCHIVED_SMOKE")
    if not location:
        pytest.skip("set QUEEN_ARCHIVED_SMOKE to the separately downloaded archive; no ZIP is published")
    path = Path(location)
    assert path.is_file(), "configured historical archive is unavailable"
    assert hashlib.sha256(path.read_bytes()).hexdigest() == META["archive_sha256"]
    return path


def changed_archive(tmp_path: Path, members: dict[str, bytes]) -> tuple[Path, str]:
    target = tmp_path / "changed.zip"
    with zipfile.ZipFile(target, "w") as archive:
        for name, body in members.items():
            archive.writestr(name, body)
    return target, hashlib.sha256(target.read_bytes()).hexdigest()


def members(recorded_archive: Path) -> dict[str, bytes]:
    with zipfile.ZipFile(recorded_archive) as archive:
        return {name: archive.read(name) for name in archive.namelist()}


def test_archived_call_verifies_without_private_key_or_new_inference(recorded_archive: Path) -> None:
    before = recorded_archive.read_bytes()
    result = verify_archive(recorded_archive, META["archive_sha256"])
    assert result["status"] == "ARCHIVED_INFERENCE_PATH_VERIFIED"
    assert result["events_verified"] == 5 and result["capability_max_calls"] == 1
    assert result["reply"] == "Mosquito." and result["output_tokens"] == 4
    assert result["requested_output_limit"] == 16
    assert result["answer_check"]["passed"] is None
    assert recorded_archive.read_bytes() == before


def test_nonempty_wrong_answer_does_not_pass_an_explicit_oracle(recorded_archive: Path) -> None:
    result = verify_archive(recorded_archive, META["archive_sha256"], "bee")
    assert result["status"] == "ARCHIVED_SMOKE_ANSWER_MISMATCH"
    assert result["answer_check"] == {"expected_word": "bee", "passed": False}
    # A positive oracle control uses the actual archived word, without relabelling
    # that word as the correct answer to the original comb-building question.
    observed = verify_archive(recorded_archive, META["archive_sha256"], "mosquito")
    assert observed["status"] == "ARCHIVED_SMOKE_PASS"


def test_retained_admissible_evidence_does_not_make_a_wrong_answer_pass(recorded_archive: Path, tmp_path: Path) -> None:
    # Offline rehearsal of admission -> retention -> answer gate. This local copy
    # does not claim that GitHub's artifact service was exercised.
    command = [sys.executable, str(SCRIPT), str(recorded_archive), "--expected-sha256", META["archive_sha256"]]
    admitted = subprocess.run(command, capture_output=True, text=True, check=False, timeout=20)
    assert admitted.returncode == 0
    assert json.loads(admitted.stdout)["status"] == "ARCHIVED_INFERENCE_PATH_VERIFIED"
    retained = tmp_path / "retained-evidence.zip"
    shutil.copyfile(recorded_archive, retained)
    result = subprocess.run(
        [*command, "--expect-word", "bee"],
        capture_output=True,
        text=True,
        check=False,
        timeout=20,
    )
    assert result.returncode == 2
    assert json.loads(result.stdout)["reply"] == "Mosquito."
    assert hashlib.sha256(retained.read_bytes()).hexdigest() == META["archive_sha256"]


def test_wrong_external_digest_is_rejected(tmp_path: Path) -> None:
    recorded_archive = tmp_path / "synthetic.zip"
    recorded_archive.write_bytes(b"synthetic bytes, not model evidence")
    with pytest.raises(ValueError, match="external receipt"):
        verify_archive(recorded_archive, "0" * 64)


@pytest.mark.parametrize("entry", ["../escape", "/absolute", "comb\\escape", "vault/keys/host.pem"])
def test_unsafe_or_private_members_are_rejected(tmp_path: Path, entry: str) -> None:
    archive, sha = changed_archive(tmp_path, {entry: b"synthetic"})
    with pytest.raises(ValueError):
        verify_archive(archive, sha)
    assert not (tmp_path / "escape").exists()


def test_private_bundle_is_also_a_nonzero_cli_result(tmp_path: Path) -> None:
    archive, sha = changed_archive(tmp_path, {"vault/keys/host.pem": b"synthetic private-file sentinel"})
    result = subprocess.run(
        [sys.executable, str(SCRIPT), str(archive), "--expected-sha256", sha],
        capture_output=True,
        text=True,
        check=False,
        timeout=20,
    )
    assert result.returncode != 0
    assert "unexpected evidence member" in result.stderr
    assert "ARCHIVED_INFERENCE_PATH_VERIFIED" not in result.stdout
    assert "synthetic private-file sentinel" not in result.stdout + result.stderr


@pytest.mark.parametrize("variant", ["symlink", "duplicate", "oversize"])
def test_ambiguous_or_oversized_zip_is_rejected(tmp_path: Path, variant: str) -> None:
    target = tmp_path / "bad.zip"
    with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        if variant == "symlink":
            info = zipfile.ZipInfo("hive.json")
            info.external_attr = (stat.S_IFLNK | 0o777) << 16
            archive.writestr(info, "outside")
        elif variant == "duplicate":
            archive.writestr("hive.json", "{}")
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", UserWarning)
                archive.writestr("hive.json", "{}")
        else:
            archive.writestr("comb/ledger.sqlite3", b"x" * (2 * 1024 * 1024 + 1))
    with pytest.raises(ValueError):
        verify_archive(target, hashlib.sha256(target.read_bytes()).hexdigest())


@pytest.mark.parametrize("mutation", ["missing_blob", "corrupt_blob", "test_mode", "tampered_ledger"])
def test_incomplete_or_changed_evidence_never_becomes_live_success(
    tmp_path: Path, mutation: str, recorded_archive: Path
) -> None:
    data = members(recorded_archive)
    if mutation == "missing_blob":
        del data[next(name for name in data if name.startswith("comb/blobs/"))]
    elif mutation == "corrupt_blob":
        data[next(name for name in data if name.startswith("comb/blobs/"))] = b"changed"
    elif mutation == "test_mode":
        manifest = json.loads(data["hive.json"])
        manifest["mode"] = "test"
        data["hive.json"] = json.dumps(manifest).encode()
    else:
        db_path = tmp_path / "ledger.sqlite3"
        db_path.write_bytes(data["comb/ledger.sqlite3"])
        with closing(sqlite3.connect(db_path)) as db, db:
            db.execute("UPDATE events SET actor='forged' WHERE seq=5")
        data["comb/ledger.sqlite3"] = db_path.read_bytes()
    archive, sha = changed_archive(tmp_path, data)
    with pytest.raises((ValueError, PermissionError, RuntimeError)):
        verify_archive(archive, sha)


def test_empty_bundle_is_not_evidence(tmp_path: Path) -> None:
    target = tmp_path / "empty.zip"
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w"):
        pass
    target.write_bytes(stream.getvalue())
    with pytest.raises(ValueError, match="missing hive"):
        verify_archive(target, hashlib.sha256(target.read_bytes()).hexdigest())
