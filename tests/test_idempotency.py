"""QOS-0001: an append can commit and then fail during readback. Replays must not duplicate it."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from queen_os.comb import HybridLogicalClock, Leases, Ledger, StaleFence
from queen_os.comb.ledger import ChainBroken, IdempotencyConflict
from queen_os.crypto import KeyRing


class Clock:
    def __init__(self) -> None:
        self.t = 10_000

    def __call__(self) -> int:
        return self.t


def ledger(tmp_path: Path, clock: Clock | None = None) -> Ledger:
    keys = KeyRing(tmp_path / "vault")
    signer = keys.load("host") if keys.exists("host") else keys.create("host")
    wall = clock or Clock()
    return Ledger(tmp_path / "l.sqlite3", HybridLogicalClock("n1", wall), signer, wall)


def test_retry_after_lost_acknowledgement_returns_the_original(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    with ledger(tmp_path) as led:
        monkeypatch.setattr(Ledger, "_post_write_fetch", lambda self, seq: (_ for _ in ()).throw(OSError("lost ack")))
        with pytest.raises(OSError):
            led.append("egg.hatched", "worker:a", {"egg": "e1", "result": "r"}, op_id="egg:e1:hatch")
        monkeypatch.undo()
        again = led.append("egg.hatched", "worker:a", {"egg": "e1", "result": "r"}, op_id="egg:e1:hatch")
        assert again.seq == 1 and again.op_id == "egg:e1:hatch"
        assert [e.seq for e in led.events()] == [1]
        assert led.find_op("egg:e1:hatch") == again
        assert led.verify_chain(require_signatures=True) == 1


def test_same_op_id_with_different_content_is_a_conflict(tmp_path: Path) -> None:
    """Two-arm: a second, different effect can't hide behind an already-used operation id."""
    with ledger(tmp_path) as led:
        led.append("egg.hatched", "worker:a", {"result": "r1"}, op_id="op-1")
        for kind, actor, payload in [
            ("egg.hatched", "worker:a", {"result": "r2"}),
            ("egg.hatched", "worker:b", {"result": "r1"}),
            ("egg.purged", "worker:a", {"result": "r1"}),
        ]:
            with pytest.raises(IdempotencyConflict):
                led.append(kind, actor, payload, op_id="op-1")
        assert led.verify_chain() == 1


def test_replay_after_fence_expiry_reads_committed_effect_but_new_ops_are_fenced(tmp_path: Path) -> None:
    clock = Clock()
    with ledger(tmp_path, clock) as led:
        lease = Leases(led).acquire("egg:e1", "worker:a", ttl_ms=100)
        first = led.append("egg.hatched", "worker:a", {"r": 1}, fence=lease.fence, op_id="op-a")
        clock.t += 1_000
        assert led.append("egg.hatched", "worker:a", {"r": 1}, fence=lease.fence, op_id="op-a") == first
        with pytest.raises(StaleFence):
            led.append("egg.hatched", "worker:a", {"r": 2}, fence=lease.fence, op_id="op-b")


def test_op_id_is_bound_into_the_chain(tmp_path: Path) -> None:
    with ledger(tmp_path) as led:
        led.append("egg.hatched", "worker:a", {"r": 1}, op_id="op-a")
    raw = sqlite3.connect(tmp_path / "l.sqlite3")
    raw.execute("UPDATE events SET op_id='op-stolen' WHERE seq=1")
    raw.commit()
    raw.close()
    with ledger(tmp_path) as led, pytest.raises(ChainBroken):
        led.verify_chain()


def test_pre_qos0001_ledgers_are_migrated(tmp_path: Path) -> None:
    db = sqlite3.connect(tmp_path / "l.sqlite3")
    db.executescript(
        "CREATE TABLE events (seq INTEGER PRIMARY KEY, event_id TEXT NOT NULL UNIQUE, hlc TEXT NOT NULL,"
        " kind TEXT NOT NULL, actor TEXT NOT NULL, payload BLOB NOT NULL, payload_sha TEXT NOT NULL,"
        " prev_hash TEXT NOT NULL, hash TEXT NOT NULL UNIQUE, signer TEXT, signature TEXT);"
    )
    db.close()
    with ledger(tmp_path) as led:
        led.append("x", "y", {}, op_id="op-1")
        assert led.find_op("op-1") is not None and led.verify_chain() == 1
