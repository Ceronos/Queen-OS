from __future__ import annotations

from pathlib import Path

import pytest

from queen_os.serial import DigestDivergence, canonicalize, digest, sha256_hex, write_canonical, write_verified


def test_write_verified_roundtrip(tmp_path: Path) -> None:
    target = tmp_path / "deep" / "x.json"
    h = write_canonical(target, {"b": 1, "a": [1.5, "é"]})
    assert target.read_bytes() == canonicalize({"a": [1.5, "é"], "b": 1})
    assert h == sha256_hex(target.read_bytes()) == digest({"b": 1, "a": [1.5, "é"]})
    assert not list(target.parent.glob(".afser-*"))


def test_divergent_storage_is_purged(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Two-arm: when the storage surface returns different bytes, nothing may remain."""
    target = tmp_path / "x.bin"
    monkeypatch.setattr(Path, "read_bytes", lambda self: b"tampered by the substrate")
    with pytest.raises(DigestDivergence):
        write_verified(target, b"intended bytes")
    monkeypatch.undo()
    assert not target.exists()
    assert not list(tmp_path.iterdir())


def test_expected_digest_mismatch_writes_nothing(tmp_path: Path) -> None:
    with pytest.raises(DigestDivergence):
        write_verified(tmp_path / "x", b"abc", expected_sha="0" * 64)
    assert not list(tmp_path.iterdir())
