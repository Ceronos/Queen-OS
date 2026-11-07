from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from queen_os.cli import main
from queen_os.crypto import KeyRing
from queen_os.hive import Hive


def test_init_open_verify(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    root = tmp_path / "hive"
    assert main(["init", str(root), "--node-id", "alpha", "--mode", "test"]) == 0
    with Hive.open(root) as hive:
        genesis = hive.ledger.get(1)
        assert genesis is not None and genesis.kind == "hive.genesis"
        assert genesis.payload["node_id"] == "alpha"
        hive.ledger.append("egg.laid", "queen", {"egg": 1})
    assert main(["ledger", "verify", str(root)]) == 0
    assert "OK 2 events verified" in capsys.readouterr().out
    assert main(["ledger", "tail", str(root), "-n", "1"]) == 0
    assert '"kind": "egg.laid"' in capsys.readouterr().out

    with pytest.raises(FileExistsError):
        Hive.init(root, "alpha")


def test_verify_exits_nonzero_on_tamper(tmp_path: Path) -> None:
    root = tmp_path / "hive"
    Hive.init(root, "alpha").close()
    db = sqlite3.connect(root / "comb" / "ledger.sqlite3")
    db.execute("UPDATE events SET actor='intruder' WHERE seq=1")
    db.commit()
    db.close()
    assert main(["ledger", "verify", str(root)]) == 2


def test_swapped_host_key_is_refused(tmp_path: Path) -> None:
    root = tmp_path / "hive"
    Hive.init(root, "alpha").close()
    key = KeyRing(root / "vault").path("host")
    key.unlink()
    KeyRing(root / "vault").create("host")
    with pytest.raises(PermissionError):
        Hive.open(root)
