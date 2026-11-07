"""Signed lease lifecycle and failed-effect recovery with synthetic workers."""

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


def make(root: Path, clock: Clock) -> Ledger:
    keys = KeyRing(root / "vault")
    signer = keys.load("host") if keys.exists("host") else keys.create("host")
    return Ledger(root / "ledger.sqlite3", HybridLogicalClock("fixture_node", clock), signer, clock)


def lease_row(ledger: Ledger) -> tuple[Any, ...]:
    with sqlite3.connect(ledger.path) as db:
        return db.execute("SELECT resource,holder,token,expires_ms FROM leases").fetchone()


@pytest.mark.parametrize("operation", ["acquire", "renew"])
@pytest.mark.parametrize("ttl", [0, -1, True, 1.5, float("nan"), "100", None])
def test_invalid_duration_never_changes_lease_or_history(tmp_path: Path, operation: str, ttl: Any) -> None:
    with make(tmp_path, Clock()) as ledger:
        leases = Leases(ledger)
        lease = leases.acquire("fixture:task", "fixture_worker", ttl_ms=100)
        row, head = lease_row(ledger), ledger.head()
        with pytest.raises(ValueError, match="positive integer"):
            if operation == "acquire":
                leases.acquire("fixture:task", "fixture_worker", ttl_ms=ttl)
            else:
                leases.renew(lease, ttl_ms=ttl)
        assert lease_row(ledger) == row and ledger.head() == head
        valid = leases.renew(lease, ttl_ms=200)
        assert valid.token == lease.token and valid.expires_ms == 1_200
        assert ledger.verify_chain(require_signatures=True) == 2


def test_renewal_updates_row_and_signed_event_together(tmp_path: Path) -> None:
    clock = Clock()
    with make(tmp_path, clock) as ledger:
        leases = Leases(ledger)
        lease = leases.acquire("fixture:task", "fixture_worker", ttl_ms=100)
        clock.t += 50
        renewed = leases.renew(lease, ttl_ms=200)
        events = list(ledger.events(kind="lease.renewed"))
        assert len(events) == 1 and events[0].actor == lease.holder
        assert events[0].payload == {"resource": lease.resource, "token": lease.token, "expires_ms": 1_250}
        assert lease_row(ledger) == (lease.resource, lease.holder, lease.token, renewed.expires_ms)
        assert ledger.verify_chain(require_signatures=True) == 2
    with make(tmp_path, clock) as recovered:
        recovered.append("fixture.done", "fixture_worker", {"fixture": True}, fence=renewed.fence)
        assert recovered.verify_chain(require_signatures=True) == 3


def test_interrupted_renewal_preserves_previous_expiry_and_event_head(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with make(tmp_path, Clock()) as ledger:
        leases = Leases(ledger)
        lease = leases.acquire("fixture:task", "fixture_worker", ttl_ms=100)
        row, head = lease_row(ledger), ledger.head()
        original = ledger.append_locked

        def interrupted(db: sqlite3.Connection, kind: str, actor: str, payload: dict[str, Any]) -> int:
            original(db, kind, actor, payload)
            raise RuntimeError("fixture renewal interrupted")

        with monkeypatch.context() as patch:
            patch.setattr(ledger, "append_locked", interrupted)
            with pytest.raises(RuntimeError, match="interrupted"):
                leases.renew(lease, ttl_ms=200)
        assert lease_row(ledger) == row and ledger.head() == head
        assert list(ledger.events(kind="lease.renewed")) == []
        leases.renew(lease, ttl_ms=200)
        assert ledger.verify_chain(require_signatures=True) == 2


def test_expired_and_superseded_renewal_cannot_change_current_grant(tmp_path: Path) -> None:
    clock = Clock()
    with make(tmp_path, clock) as ledger:
        leases = Leases(ledger)
        old = leases.acquire("fixture:task", "fixture_worker_a", ttl_ms=100)
        clock.t = old.expires_ms
        row, head = lease_row(ledger), ledger.head()
        with pytest.raises(StaleFence):
            leases.renew(old, ttl_ms=200)
        assert lease_row(ledger) == row and ledger.head() == head
        new = leases.acquire(old.resource, "fixture_worker_b", ttl_ms=100)
        row, head = lease_row(ledger), ledger.head()
        with pytest.raises(StaleFence):
            leases.renew(old, ttl_ms=200)
        assert lease_row(ledger) == row and ledger.head() == head
        leases.renew(new, ttl_ms=200)
        assert ledger.verify_chain(require_signatures=True) == 3


@pytest.mark.parametrize("operation", ["acquire", "renew", "release"])
def test_lease_post_commit_readback_failure_is_an_uncertain_effect(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, operation: str
) -> None:
    clock = Clock()
    with make(tmp_path, clock) as ledger:
        leases = Leases(ledger)
        initial = None if operation == "acquire" else leases.acquire("fixture:task", "fixture_worker", ttl_ms=100)

        def unreadable(seq: int) -> None:
            raise OSError("fixture lease readback unavailable")

        with monkeypatch.context() as patch:
            patch.setattr(ledger, "_post_write_fetch", unreadable)
            with pytest.raises(OSError, match="readback unavailable"):
                if operation == "acquire":
                    leases.acquire("fixture:task", "fixture_worker", ttl_ms=100)
                elif operation == "renew":
                    assert initial is not None
                    leases.renew(initial, ttl_ms=200)
                else:
                    assert initial is not None
                    leases.release(initial)
    with make(tmp_path, clock) as recovered:
        kind = {"acquire": "lease.granted", "renew": "lease.renewed", "release": "lease.released"}[operation]
        assert len(list(recovered.events(kind=kind))) == 1
        expected_expiry = {"acquire": 1_100, "renew": 1_200, "release": 0}[operation]
        assert lease_row(recovered) == ("fixture:task", "fixture_worker", 1, expected_expiry)
        assert recovered.verify_chain(require_signatures=True) == (1 if operation == "acquire" else 2)
