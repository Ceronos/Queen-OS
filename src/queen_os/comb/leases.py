"""Atomic leases with monotonic fencing tokens.

V1 failure (REMEDY §1.2): agents could not atomically claim a task, so tools ran twice.
Here a claim is a lease row plus a ledger event, written in one SQLite transaction.
Every grant of a resource increments its token. Writes carry the token as a fence
(:meth:`Ledger.append(fence=...)`), so a holder whose lease lapsed, whether paused,
partitioned or slow, is rejected even if it still believes it holds the lease.
"""

from __future__ import annotations

from dataclasses import dataclass

from queen_os.comb.ledger import Ledger, LedgerError


class LeaseHeld(LedgerError):
    pass


@dataclass(frozen=True)
class Lease:
    resource: str
    holder: str
    token: int
    expires_ms: int

    @property
    def fence(self) -> tuple[str, int]:
        return (self.resource, self.token)


class Leases:
    def __init__(self, ledger: Ledger) -> None:
        self.ledger = ledger

    def acquire(self, resource: str, holder: str, ttl_ms: int) -> Lease:
        if type(ttl_ms) is not int or ttl_ms <= 0:
            raise ValueError("ttl_ms must be a positive integer")
        with self.ledger.transaction() as db:
            now = self.ledger.now()
            row = db.execute("SELECT holder, token, expires_ms FROM leases WHERE resource=?", (resource,)).fetchone()
            if row is not None and row[2] > now and row[0] != holder:
                raise LeaseHeld(f"{resource} held by {row[0]} until {row[2]}")
            token = 1 if row is None else row[1] + 1
            expires = now + ttl_ms
            db.execute(
                "INSERT INTO leases(resource, holder, token, expires_ms) VALUES (?,?,?,?)"
                " ON CONFLICT(resource) DO UPDATE SET holder=excluded.holder, token=excluded.token,"
                " expires_ms=excluded.expires_ms",
                (resource, holder, token, expires),
            )
            seq = self.ledger.append_locked(
                db, "lease.granted", holder, {"resource": resource, "token": token, "expires_ms": expires}
            )
        self.ledger._post_write_fetch(seq)
        return Lease(resource, holder, token, expires)

    def renew(self, lease: Lease, ttl_ms: int) -> Lease:
        """Set a live lease's lifetime from now, retaining its token and recording the change."""
        if type(ttl_ms) is not int or ttl_ms <= 0:
            raise ValueError("ttl_ms must be a positive integer")
        with self.ledger.transaction() as db:
            self.ledger.check_fence(db, *lease.fence)
            expires = self.ledger.now() + ttl_ms
            db.execute("UPDATE leases SET expires_ms=? WHERE resource=?", (expires, lease.resource))
            seq = self.ledger.append_locked(
                db,
                "lease.renewed",
                lease.holder,
                {"resource": lease.resource, "token": lease.token, "expires_ms": expires},
            )
        self.ledger._post_write_fetch(seq)
        return Lease(lease.resource, lease.holder, lease.token, expires)

    def release(self, lease: Lease) -> None:
        with self.ledger.transaction() as db:
            self.ledger.check_fence(db, *lease.fence)
            db.execute("UPDATE leases SET expires_ms=0 WHERE resource=?", (lease.resource,))
            seq = self.ledger.append_locked(
                db, "lease.released", lease.holder, {"resource": lease.resource, "token": lease.token}
            )
        self.ledger._post_write_fetch(seq)
