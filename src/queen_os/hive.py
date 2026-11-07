"""A Hive: one Queen-OS instance on disk. It bundles enclaves, ledger, blobs, leases and host identity."""

from __future__ import annotations

import json
import os
import platform
import sys
from dataclasses import dataclass
from pathlib import Path

from queen_os import __version__
from queen_os.authority.tokens import Authority
from queen_os.comb.blobs import BlobStore
from queen_os.comb.enclaves import Enclaves
from queen_os.comb.hlc import HybridLogicalClock, validate_node_id
from queen_os.comb.leases import Leases
from queen_os.comb.ledger import Ledger
from queen_os.crypto.keys import KeyRing
from queen_os.serial.afser import write_verified
from queen_os.serial.jcs import canonicalize

HIVE_MANIFEST = "hive.json"


def default_home() -> Path:
    env = os.environ.get("QUEEN_HOME")
    return Path(env).expanduser() if env else Path.home() / ".queen-os"


@dataclass
class Hive:
    root: Path
    node_id: str
    mode: str
    enclaves: Enclaves
    ledger: Ledger
    blobs: BlobStore
    leases: Leases

    @classmethod
    def init(cls, root: Path, node_id: str, mode: str = "production") -> Hive:
        if mode not in ("production", "test"):
            raise ValueError("mode must be 'production' or 'test'")
        root = root.resolve()
        if (root / HIVE_MANIFEST).exists():
            raise FileExistsError(f"{root} is already a hive")
        validate_node_id(node_id)
        enclaves = Enclaves(root)
        enclaves.create()
        keyring = KeyRing(enclaves.vault)
        signer = keyring.create("host")
        manifest = {"format": 1, "node_id": node_id, "mode": mode, "host_key_id": signer.key_id}
        write_verified(root / HIVE_MANIFEST, canonicalize(manifest))
        hive = cls.open(root)
        hive.ledger.append(
            "hive.genesis",
            f"host:{node_id}",
            {
                "node_id": node_id,
                "mode": mode,
                "queen_os": __version__,
                "python": platform.python_version(),
                "os": sys.platform,
                "machine": platform.machine(),
                "host_key_id": signer.key_id,
            },
        )
        return hive

    @classmethod
    def open(cls, root: Path) -> Hive:
        root = root.resolve()
        manifest = json.loads((root / HIVE_MANIFEST).read_bytes())
        node_id = manifest["node_id"]
        enclaves = Enclaves(root)
        signer = KeyRing(enclaves.vault).load("host")
        if signer.key_id != manifest["host_key_id"]:
            raise PermissionError("host key does not match hive manifest")
        ledger = Ledger(root / "comb" / "ledger.sqlite3", HybridLogicalClock(node_id), signer)
        blobs = BlobStore(root / "comb" / "blobs")
        return cls(root, node_id, manifest["mode"], enclaves, ledger, blobs, Leases(ledger))

    def authority(self) -> Authority:
        """The hive's capability issuer and checker, keyed by the host identity."""
        if self.ledger.signer is None:
            raise PermissionError("hive opened without a host signer")
        return Authority(self.ledger, self.ledger.signer)

    def close(self) -> None:
        self.ledger.close()

    def __enter__(self) -> Hive:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()
