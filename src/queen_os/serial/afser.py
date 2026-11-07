"""AF-SER-V1: canonicalize, digest, write, re-fetch, re-digest, assert.

The six steps from the Pillar 2 spec, made portable: ``os.replace`` is atomic on
Windows, macOS and Linux, and ``fsync`` is called on the file. On POSIX the parent
directory is fsynced too, so the rename itself is durable.
"""

from __future__ import annotations

import hashlib
import os
import sys
import tempfile
from pathlib import Path
from typing import Any

from queen_os.serial.jcs import canonicalize


class DigestDivergence(RuntimeError):
    """H_local != H_fetched. The write is purged and the caller must fail closed."""


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def digest(value: Any) -> str:
    """SHA-256 over the JCS bytes of ``value``."""
    return sha256_hex(canonicalize(value))


def fsync_dir(path: Path) -> None:
    if sys.platform == "win32":
        return  # NTFS directory handles cannot be fsynced; MoveFileEx is journaled.
    fd = os.open(path, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def write_verified(target: Path, data: bytes, expected_sha: str | None = None) -> str:
    """Write ``data`` to ``target`` atomically, then re-read it and prove the bytes landed.

    Returns the SHA-256 hex digest. Raises :class:`DigestDivergence` (after removing
    whatever was written) if the stored bytes differ from what was intended.
    """
    h_local = sha256_hex(data)
    if expected_sha is not None and expected_sha != h_local:
        raise DigestDivergence(f"payload digest {h_local} != expected {expected_sha}")
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(dir=target.parent, prefix=".afser-", suffix=".tmp")
    tmp = Path(tmp_name)
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
            fh.flush()
            os.fsync(fh.fileno())
        _assert_stored(tmp, h_local)
        os.replace(tmp, target)
        fsync_dir(target.parent)
        _assert_stored(target, h_local)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise
    return h_local


def write_canonical(target: Path, value: Any) -> str:
    return write_verified(target, canonicalize(value))


def _assert_stored(path: Path, h_local: str) -> None:
    h_fetched = sha256_hex(path.read_bytes())
    if h_fetched != h_local:
        path.unlink(missing_ok=True)
        raise DigestDivergence(f"AF-SER-V1 divergence at {path}: local {h_local} != fetched {h_fetched}")
