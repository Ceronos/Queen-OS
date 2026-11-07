"""Ed25519 identities (the "Dufour gland"): host, queen and partner signing keys.

A signature proves *origin*, never *truth*. Correctness comes from the
VerificationGate; signatures only make the ledger tamper-evident and attributable.
"""

from __future__ import annotations

import hashlib
import os
import sys
from dataclasses import dataclass
from pathlib import Path

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey

_RAW = serialization.Encoding.Raw
_RAW_PUB = serialization.PublicFormat.Raw


def key_id(public: Ed25519PublicKey) -> str:
    return hashlib.sha256(public.public_bytes(_RAW, _RAW_PUB)).hexdigest()[:16]


@dataclass(frozen=True)
class Signer:
    name: str
    private: Ed25519PrivateKey

    @property
    def public(self) -> Ed25519PublicKey:
        return self.private.public_key()

    @property
    def key_id(self) -> str:
        return key_id(self.public)

    def sign(self, message: bytes) -> str:
        return self.private.sign(message).hex()


def verify(public: Ed25519PublicKey, message: bytes, signature_hex: str) -> bool:
    try:
        public.verify(bytes.fromhex(signature_hex), message)
    except (InvalidSignature, ValueError):
        return False
    return True


def public_from_hex(raw_hex: str) -> Ed25519PublicKey:
    return Ed25519PublicKey.from_public_bytes(bytes.fromhex(raw_hex))


def public_to_hex(public: Ed25519PublicKey) -> str:
    return public.public_bytes(_RAW, _RAW_PUB).hex()


class KeyRing:
    """Private keys stored under the hive's ``vault`` enclave.

    POSIX: files are created 0600. Windows: files inherit the user-profile ACL.
    Hardware-backed keys (FIDO2/YubiKey, TPM) are T2 providers, planned for M3.
    """

    def __init__(self, vault: Path) -> None:
        self.dir = vault / "keys"

    def path(self, name: str) -> Path:
        if not name.isidentifier():
            raise ValueError(f"invalid key name {name!r}")
        return self.dir / f"{name}.ed25519.pem"

    def exists(self, name: str) -> bool:
        return self.path(name).exists()

    def create(self, name: str) -> Signer:
        target = self.path(name)
        if target.exists():
            raise FileExistsError(f"key {name!r} already exists; refusing to overwrite an identity")
        self.dir.mkdir(parents=True, exist_ok=True)
        private = Ed25519PrivateKey.generate()
        pem = private.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0)
        fd = os.open(target, flags, 0o600)
        with os.fdopen(fd, "wb") as fh:
            fh.write(pem)
            fh.flush()
            os.fsync(fh.fileno())
        return Signer(name, private)

    def load(self, name: str) -> Signer:
        target = self.path(name)
        if sys.platform != "win32" and target.stat().st_mode & 0o077:
            raise PermissionError(f"{target} is readable by group/other; fix with chmod 600")
        private = serialization.load_pem_private_key(target.read_bytes(), password=None)
        if not isinstance(private, Ed25519PrivateKey):
            raise TypeError(f"{target} is not an Ed25519 key")
        return Signer(name, private)
