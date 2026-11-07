"""Content-addressed blob store. The address *is* the SHA-256, so a reference can't drift."""

from __future__ import annotations

import re
from pathlib import Path

from queen_os.serial.afser import DigestDivergence, sha256_hex, write_verified

_SHA_RE = re.compile(r"^[0-9a-f]{64}$")


class BlobStore:
    def __init__(self, root: Path) -> None:
        self.root = root

    def _path(self, sha: str) -> Path:
        if not _SHA_RE.match(sha):
            raise ValueError(f"not a sha256 hex digest: {sha!r}")
        return self.root / sha[:2] / sha

    def put(self, data: bytes) -> str:
        sha = sha256_hex(data)
        target = self._path(sha)
        if target.exists() and sha256_hex(target.read_bytes()) == sha:
            return sha
        return write_verified(target, data, expected_sha=sha)

    def get(self, sha: str) -> bytes:
        data = self._path(sha).read_bytes()
        if sha256_hex(data) != sha:
            raise DigestDivergence(f"blob {sha} is corrupt on disk")
        return data

    def has(self, sha: str) -> bool:
        return self._path(sha).exists()
