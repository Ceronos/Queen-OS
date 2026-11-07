"""Offline interruption/reopen contracts with generated keys and synthetic work.

These exercise real SQLite and signatures. Injected Python exceptions and clean
connection reopen are not evidence of power-loss durability or OS containment.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

import pytest

from queen_os.comb import HybridLogicalClock, Leases, Ledger, StaleFence
from queen_os.crypto import KeyRing


class Clock:
    def __init__(self) -> None:
        self.t = 1_000

    def __call__(self) -> int:
        return self.t


def open_ledger(root: Path, clock: Clock) -> Ledger:
    keys = KeyRing(root / "vault")
    signer = keys.load("host") if keys.exists("host") else keys.create("host")
    return Ledger(root / "ledger.sqlite3", HybridLogicalClock("fixture_node", clock), signer, clock)


@pytest.mark.parametrize("failure", [RuntimeError, KeyboardInterrupt])
def test_interrupted_lease_grant_rolls_back_row_and_event(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, failure: type[BaseException]
) -> None:
    clock = Clock()
    with open_ledger(tmp_path, clock) as ledger:
        ledger.append("fixture.started", "fixture_controller", {"fixture": True})
        original = ledger.append_locked

        def interrupted(db: sqlite3.Connection, kind: str, actor: str, payload: dict[str, Any]) -> int:
            original(db, kind, actor, payload)  # fail after both INSERTs, before COMMIT
            raise failure("fixture interruption before commit")

        with monkeypatch.context() as patch:
            patch.setattr(ledger, "append_locked", interrupted)
            with pytest.raises(failure, match="before commit"):
                Leases(ledger).acquire("fixture:task", "fixture_worker_a", ttl_ms=100)

    with open_ledger(tmp_path, clock) as recovered:
        assert recovered.verify_chain(require_signatures=True) == 1
        assert list(recovered.events(kind="lease.granted")) == []
        with sqlite3.connect(recovered.path) as raw:
            assert raw.execute("SELECT COUNT(*) FROM leases").fetchone()[0] == 0
        lease = Leases(recovered).acquire("fixture:task", "fixture_worker_b", ttl_ms=100)
        assert lease.token == 1  # rolled-back grant consumed neither row nor token
        event = recovered.append("fixture.done", "fixture_worker_b", {"fixture": True}, fence=lease.fence)
        assert event.seq == 3
        assert recovered.verify_chain(require_signatures=True) == 3


def test_post_commit_readback_failure_requires_read_before_any_retry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    clock = Clock()
    payload = {"fixture": True, "operation_id": "synthetic-operation-001", "result": 91}
    with open_ledger(tmp_path, clock) as ledger:
        lease = Leases(ledger).acquire("fixture:task", "fixture_worker_a", ttl_ms=100)

        def unreadable(seq: int) -> None:
            raise OSError("fixture readback unavailable after commit")

        with monkeypatch.context() as patch:
            patch.setattr(ledger, "_post_write_fetch", unreadable)
            with pytest.raises(OSError, match="after commit"):
                ledger.append("fixture.done", "fixture_worker_a", payload, fence=lease.fence)

    # An exception at the caller did not mean the effect was absent. Reopen and
    # reconcile stored evidence instead of automatically repeating the append.
    with open_ledger(tmp_path, clock) as recovered:
        results = list(recovered.events(kind="fixture.done"))
        assert len(results) == 1 and results[0].payload == payload
        assert results[0].signer is not None
        assert recovered.verify_chain(require_signatures=True) == 2
        head = recovered.head()
        assert head is not None and head.event_id == results[0].event_id
        acknowledgement = recovered.append(
            "fixture.reconciled", "fixture_controller", {"fixture": True, "event_id": results[0].event_id}
        )
        assert acknowledgement.seq == 3 and acknowledgement.prev_hash == results[0].hash
        assert len(list(recovered.events(kind="fixture.done"))) == 1
        assert recovered.verify_chain(require_signatures=True) == 3


def test_reopened_stale_worker_cannot_write_after_expiry_or_takeover(tmp_path: Path) -> None:
    clock = Clock()
    with open_ledger(tmp_path, clock) as ledger:
        old = Leases(ledger).acquire("fixture:task", "fixture_worker_a", ttl_ms=100)
        ledger.append("fixture.progress", "fixture_worker_a", {"fixture": True}, fence=old.fence)

    clock.t = old.expires_ms  # exact boundary, not just a much-later clock value
    with open_ledger(tmp_path, clock) as recovered:
        head = recovered.head()
        assert head is not None
        with pytest.raises(StaleFence):
            recovered.append("fixture.done", "fixture_worker_a", {"fixture": True}, fence=old.fence)
        assert recovered.head() == head
        current = Leases(recovered).acquire("fixture:task", "fixture_worker_b", ttl_ms=100)
        assert current.token == old.token + 1

    with open_ledger(tmp_path, clock) as restarted:
        head = restarted.head()
        with pytest.raises(StaleFence):
            restarted.append("fixture.done", "fixture_worker_a", {"fixture": True}, fence=old.fence)
        assert restarted.head() == head
        done = restarted.append("fixture.done", "fixture_worker_b", {"fixture": True}, fence=current.fence)
        assert done.seq == 4
        assert restarted.verify_chain(require_signatures=True) == 4


def test_invalid_payload_does_not_consume_sequence_or_live_lease(tmp_path: Path) -> None:
    clock = Clock()
    with open_ledger(tmp_path, clock) as ledger:
        lease = Leases(ledger).acquire("fixture:task", "fixture_worker_a", ttl_ms=100)
        head = ledger.head()
        with pytest.raises(ValueError):
            ledger.append(
                "fixture.done", "fixture_worker_a", {"fixture": True, "result": float("nan")}, fence=lease.fence
            )
        assert ledger.head() == head

    # A newly constructed HLC/connection must continue from the persisted head,
    # including when wall time regresses while the lease is still live.
    clock.t -= 1
    with open_ledger(tmp_path, clock) as recovered:
        done = recovered.append("fixture.done", "fixture_worker_a", {"fixture": True, "result": 91}, fence=lease.fence)
        assert head is not None
        assert done.seq == head.seq + 1 and done.prev_hash == head.hash and done.hlc > head.hlc
        renewed = Leases(recovered).renew(lease, ttl_ms=200)
        assert renewed.token == lease.token and renewed.expires_ms > lease.expires_ms
        assert recovered.verify_chain(require_signatures=True) == 2
