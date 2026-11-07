"""The five spatial enclaves of a hive (Thesis §4.2).

    workspace/   transient scratch for workers
    staging/     candidates awaiting the VerificationGate
    committed/   promoted artifacts; made read-only on promotion
    quarantine/  purged artifacts (oophagy); never executed
    vault/       keys and sealed material

M0 enforces these policies in-process and on the filesystem with plain permission
bits. OS-level enforcement (Landlock, Job Objects, sandbox-exec) is a T2 host provider
planned for M3, so these boundaries hold against bugs but not yet against a
hostile local process.
"""

from __future__ import annotations

import os
import re
import stat
from dataclasses import dataclass
from pathlib import Path

from queen_os.serial.afser import DigestDivergence, fsync_dir, sha256_hex, write_verified

ENCLAVES = ("workspace", "staging", "committed", "quarantine", "vault")
_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")


class EnclaveViolation(PermissionError):
    pass


def safe_name(name: str) -> str:
    if not _NAME_RE.match(name) or ".." in name:
        raise EnclaveViolation(f"artifact name {name!r} is not a safe flat filename")
    return name


@dataclass(frozen=True)
class Enclaves:
    root: Path

    def __getattr__(self, item: str) -> Path:
        if item in ENCLAVES:
            return self.root / item
        raise AttributeError(item)

    def create(self) -> None:
        for name in ENCLAVES:
            (self.root / name).mkdir(parents=True, exist_ok=True)
        if os.name == "posix":
            os.chmod(self.root / "vault", 0o700)

    def stage(self, name: str, data: bytes) -> str:
        """Write a candidate into staging with post-write fetch. Returns its digest."""
        return write_verified(self.root / "staging" / safe_name(name), data)

    def promote(self, name: str, expected_sha: str) -> Path:
        """staging → committed, only with the exact bytes the gate approved (QOS-0009).

        1. Read staging once and hash it, so the approved digest refers to *these* bytes.
        2. Write those bytes (not the file, which could still change) to a temp file in committed/.
        3. Publish with ``os.link``: atomic and **no-replace** on POSIX and NTFS. If two promoters race,
           exactly one wins, and an existing committed artifact can never be overwritten.
        4. Re-read and verify, mark read-only, then remove the staging copy.
        """
        src = self.root / "staging" / safe_name(name)
        dst = self.root / "committed" / name
        data = src.read_bytes()
        actual = sha256_hex(data)
        if actual != expected_sha:
            raise DigestDivergence(f"staging/{name} changed after approval: {actual} != {expected_sha}")
        tmp = self.root / "committed" / f".promote-{os.getpid()}-{os.urandom(6).hex()}.tmp"
        write_verified(tmp, data, expected_sha=expected_sha)
        try:
            os.link(tmp, dst)
        except FileExistsError:
            raise EnclaveViolation(f"committed/{name} already exists; committed state is immutable") from None
        finally:
            tmp.unlink(missing_ok=True)
        fsync_dir(dst.parent)
        if sha256_hex(dst.read_bytes()) != expected_sha:
            raise DigestDivergence(f"committed/{name} diverged after promotion")
        os.chmod(dst, stat.S_IREAD | stat.S_IRGRP | stat.S_IROTH)
        src.unlink(missing_ok=True)
        return dst

    def quarantine(self, name: str, enclave: str = "staging") -> Path:
        """Atomically move an artifact into quarantine (oophagy). Returns the tombstone path."""
        if enclave not in ("workspace", "staging"):
            raise EnclaveViolation("only workspace/staging artifacts can be purged")
        src = self.root / enclave / safe_name(name)
        dst = self.root / "quarantine" / f"{name}.quarantine"
        os.replace(src, dst)
        os.chmod(dst, stat.S_IREAD)
        fsync_dir(dst.parent)
        return dst
