"""Real SQLite failure paths; no providers or live credentials."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

import pytest

from queen_os.comb import HybridLogicalClock, Ledger
from queen_os.crypto import KeyRing


def make(root: Path) -> Ledger:
    keys = KeyRing(root / "vault")
    signer = keys.load("host") if keys.exists("host") else keys.create("host")
    return Ledger(root / "ledger.sqlite3", HybridLogicalClock("fixture_node"), signer)


def test_failed_commit_rolls_back_and_connection_can_accept_next_write(tmp_path: Path) -> None:
    with make(tmp_path) as ledger:
        with ledger.transaction() as db:
            db.execute("CREATE TABLE fixture_parent (id INTEGER PRIMARY KEY)")
            db.execute(
                "CREATE TABLE fixture_child (parent_id INTEGER REFERENCES fixture_parent(id)"
                " DEFERRABLE INITIALLY DEFERRED)"
            )
        body_finished = False
        with pytest.raises(sqlite3.IntegrityError, match="FOREIGN KEY"), ledger.transaction() as db:
            db.execute("INSERT INTO fixture_child VALUES (99)")
            ledger.append_locked(db, "fixture.pending", "fixture_worker", {"fixture": True})
            body_finished = True  # the actual COMMIT, not the body, must fail
        assert body_finished and not ledger._db.in_transaction
        assert ledger._db.execute("SELECT COUNT(*) FROM fixture_child").fetchone()[0] == 0
        assert ledger.head() is None
        event = ledger.append("fixture.done", "fixture_worker", {"fixture": True})
        assert event.seq == 1 and ledger.verify_chain(require_signatures=True) == 1


def test_sqlite_automatic_rollback_does_not_mask_original_error(tmp_path: Path) -> None:
    with make(tmp_path) as ledger:
        with ledger.transaction() as db:
            db.execute("CREATE TABLE fixture_unique (value INTEGER UNIQUE)")
            db.execute("INSERT INTO fixture_unique VALUES (1)")
        with pytest.raises(sqlite3.IntegrityError, match="UNIQUE constraint"), ledger.transaction() as db:
            ledger.append_locked(db, "fixture.pending", "fixture_worker", {"fixture": True})
            db.execute("INSERT OR ROLLBACK INTO fixture_unique VALUES (1)")
        assert not ledger._db.in_transaction and ledger.head() is None
        event = ledger.append("fixture.done", "fixture_worker", {"fixture": True})
        assert event.seq == 1 and ledger.verify_chain(require_signatures=True) == 1


def test_cleanup_failure_preserves_primary_error_and_discards_connection(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ledger = make(tmp_path)
    real = ledger._db

    class BrokenRollback:
        """Inject only a rollback I/O failure; all writes use the real database."""

        def __getattr__(self, name: str) -> Any:
            return getattr(real, name)

        def execute(self, sql: str) -> Any:
            if sql == "ROLLBACK":
                raise sqlite3.OperationalError("fixture rollback failure")
            return real.execute(sql)

    try:
        with monkeypatch.context() as patch:
            patch.setattr(ledger, "_db", BrokenRollback())
            with pytest.raises(RuntimeError, match="fixture primary error") as caught, ledger.transaction():
                ledger.append_locked(real, "fixture.pending", "fixture_worker", {"fixture": True})
                raise RuntimeError("fixture primary error")
            assert any("reopen" in note.lower() for note in caught.value.__notes__)
        with pytest.raises(sqlite3.ProgrammingError, match="closed"):
            real.execute("SELECT 1")
    finally:
        ledger.close()
    with make(tmp_path) as recovered:
        assert recovered.head() is None
        recovered.append("fixture.done", "fixture_worker", {"fixture": True})
        assert recovered.verify_chain(require_signatures=True) == 1
