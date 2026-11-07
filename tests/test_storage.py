from __future__ import annotations

import os
import stat
from pathlib import Path

import pytest

from queen_os.comb import BlobStore, Enclaves, EnclaveViolation
from queen_os.serial import DigestDivergence, sha256_hex


def test_blob_store_content_addressing(tmp_path: Path) -> None:
    store = BlobStore(tmp_path)
    sha = store.put(b"pollen")
    assert sha == sha256_hex(b"pollen") and store.put(b"pollen") == sha
    assert store.get(sha) == b"pollen"
    path = tmp_path / sha[:2] / sha
    os.chmod(path, 0o644)
    path.write_bytes(b"bitrot")
    with pytest.raises(DigestDivergence):
        store.get(sha)
    with pytest.raises(ValueError):
        store.get("../../etc/passwd")


def test_enclave_promotion_requires_unchanged_bytes(tmp_path: Path) -> None:
    enc = Enclaves(tmp_path)
    enc.create()
    sha = enc.stage("egg-1.json", b'{"ok":true}')
    committed = enc.promote("egg-1.json", sha)
    assert committed.read_bytes() == b'{"ok":true}'
    assert not committed.stat().st_mode & stat.S_IWUSR
    with pytest.raises(EnclaveViolation):
        enc.stage("egg-1.json", b"x") and enc.promote("egg-1.json", sha256_hex(b"x"))

    sha2 = enc.stage("egg-2.json", b"approved")
    (tmp_path / "staging" / "egg-2.json").write_bytes(b"swapped after approval")
    with pytest.raises(DigestDivergence):
        enc.promote("egg-2.json", sha2)
    tomb = enc.quarantine("egg-2.json")
    assert tomb.parent.name == "quarantine" and not (tmp_path / "staging" / "egg-2.json").exists()


@pytest.mark.parametrize("name", ["../escape", "a/b", "a\\b", "..", ".hidden", "", "x" * 200])
def test_unsafe_artifact_names_fail_closed(tmp_path: Path, name: str) -> None:
    enc = Enclaves(tmp_path)
    enc.create()
    with pytest.raises(EnclaveViolation):
        enc.stage(name, b"payload")
    assert not any(list((tmp_path / d).iterdir()) for d in ("workspace", "staging", "committed"))
