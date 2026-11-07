"""QueenStore: the append-only, hash-chained, HLC-ordered event ledger.

Every coordination act in a hive (a task egg laid, a lease granted, an artifact
promoted, a purge) is an event here. Agents never message each other. They read the
fold of this ledger and append to it. That is the stigmergy.

Guarantees, all tested:

* **Chain:** ``hash_n = SHA-256(JCS(header_n))`` where the header binds seq, event id,
  HLC, kind, actor, payload digest and ``hash_{n-1}``, starting from ``GENESIS_ROOT``.
* **Serialized writers across processes:** ``BEGIN IMMEDIATE`` takes SQLite's
  reserved lock, so two processes can never both extend the same head.
* **Post-write fetch (AF-SER-V1 steps 4–6):** after COMMIT the row is read back and
  its hash recomputed from the stored bytes. A mismatch raises.
* **Fencing:** an append can name a ``(resource, token)`` fence. It is admitted only
  if that token is still the live lease, so a paused or partitioned stale holder
  cannot write.
* **Signatures:** if the ledger has a signer, each event hash is Ed25519-signed by
  the host key.
"""

from __future__ import annotations

import json
import sqlite3
import time
import uuid
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from queen_os.comb.hlc import HLCStamp, HybridLogicalClock
from queen_os.crypto.keys import Signer, public_from_hex, public_to_hex, verify
from queen_os.serial.afser import sha256_hex
from queen_os.serial.jcs import canonicalize

GENESIS_ROOT = "GENESIS_ROOT_0000000000000000"
SCHEMA_VERSION = 1

_SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS events (
    seq         INTEGER PRIMARY KEY,
    event_id    TEXT NOT NULL UNIQUE,
    hlc         TEXT NOT NULL,
    kind        TEXT NOT NULL,
    actor       TEXT NOT NULL,
    payload     BLOB NOT NULL,
    payload_sha TEXT NOT NULL,
    prev_hash   TEXT NOT NULL,
    hash        TEXT NOT NULL UNIQUE,
    signer      TEXT,
    signature   TEXT,
    op_id       TEXT UNIQUE
);
CREATE INDEX IF NOT EXISTS events_kind ON events(kind);
CREATE TABLE IF NOT EXISTS signers (key_id TEXT PRIMARY KEY, name TEXT NOT NULL, public_hex TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS leases (
    resource   TEXT PRIMARY KEY,
    holder     TEXT NOT NULL,
    token      INTEGER NOT NULL,
    expires_ms INTEGER NOT NULL
);
"""


class LedgerError(RuntimeError):
    pass


class StaleFence(LedgerError):
    """The writer's fencing token is no longer the live lease. Fail closed."""


class ChainBroken(LedgerError):
    pass


class IdempotencyConflict(LedgerError):
    """An ``op_id`` was replayed with different content. Two different effects claim one operation."""


@dataclass(frozen=True)
class Event:
    seq: int
    event_id: str
    hlc: str
    kind: str
    actor: str
    payload: dict[str, Any]
    payload_sha: str
    prev_hash: str
    hash: str
    signer: str | None
    signature: str | None
    op_id: str | None = None


def _header(
    seq: int, event_id: str, hlc: str, kind: str, actor: str, payload_sha: str, prev: str, op_id: str | None = None
) -> bytes:
    header: dict[str, Any] = {
        "actor": actor,
        "event_id": event_id,
        "hlc": hlc,
        "kind": kind,
        "payload_sha": payload_sha,
        "prev_hash": prev,
        "seq": seq,
        "v": SCHEMA_VERSION,
    }
    if op_id is not None:  # bound into the chain, so an op_id cannot be reassigned after the fact
        header["op_id"] = op_id
    return canonicalize(header)


def now_ms() -> int:
    return time.time_ns() // 1_000_000


class Ledger:
    def __init__(
        self,
        path: Path,
        clock: HybridLogicalClock,
        signer: Signer | None = None,
        wall_ms: Callable[[], int] = now_ms,
    ) -> None:
        self.path = path
        self.clock = clock
        self.signer = signer
        self._wall_ms = wall_ms
        path.parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(path, isolation_level=None, timeout=30.0)
        self._db.execute("PRAGMA journal_mode=WAL")
        self._db.execute("PRAGMA synchronous=FULL")
        self._db.execute("PRAGMA foreign_keys=ON")
        self._db.executescript(_SCHEMA)
        self._migrate()
        if signer is not None:
            self._register_signer(signer)

    def now(self) -> int:
        return self._wall_ms()

    def close(self) -> None:
        self._db.close()

    def __enter__(self) -> Ledger:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    # -- transactions -------------------------------------------------------------

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        """Exclusive-writer transaction. Every mutation of the comb goes through here."""
        self._db.execute("BEGIN IMMEDIATE")
        try:
            yield self._db
            self._db.execute("COMMIT")
        except BaseException as primary:
            try:
                # COMMIT can fail with a transaction still open; SQLite can
                # also roll back on its own before raising from the body.
                if self._db.in_transaction:
                    self._db.execute("ROLLBACK")
            except BaseException:
                primary.add_note("Transaction cleanup failed; discard this connection and reopen to reconcile effects.")
                try:
                    self._db.close()
                except BaseException:
                    primary.add_note("Closing the failed connection also failed; do not reuse it.")
            raise

    def _migrate(self) -> None:
        cols = {row[1] for row in self._db.execute("PRAGMA table_info(events)")}
        if "op_id" not in cols:  # ledgers created before QOS-0001
            with self.transaction() as db:
                db.execute("ALTER TABLE events ADD COLUMN op_id TEXT")
                db.execute("CREATE UNIQUE INDEX IF NOT EXISTS events_op_id ON events(op_id)")

    def _register_signer(self, signer: Signer) -> None:
        with self.transaction() as db:
            db.execute(
                "INSERT OR IGNORE INTO signers(key_id, name, public_hex) VALUES (?,?,?)",
                (signer.key_id, signer.name, public_to_hex(signer.public)),
            )

    # -- append -------------------------------------------------------------------

    def append(
        self,
        kind: str,
        actor: str,
        payload: dict[str, Any],
        *,
        fence: tuple[str, int] | None = None,
        op_id: str | None = None,
    ) -> Event:
        """Append one event.

        With ``op_id``, the append is idempotent (QOS-0001): if the operation already committed,
        possibly in an attempt whose caller saw an exception, the original event is returned
        and nothing new is written. A replay with different kind/actor/payload raises
        :class:`IdempotencyConflict`. A replay is a read of an effect that already
        committed, so it is answered even if the fence has since expired.
        """
        with self.transaction() as db:
            if op_id is not None:
                prior = self._prior_op(db, op_id, kind, actor, payload)
                if prior is not None:
                    return self._post_write_fetch_after(db, prior)
            if fence is not None:
                self.check_fence(db, *fence)
            seq = self.append_locked(db, kind, actor, payload, op_id=op_id)
        return self._post_write_fetch(seq)

    def _post_write_fetch_after(self, db: sqlite3.Connection, seq: int) -> Event:
        row = db.execute("SELECT * FROM events WHERE seq=?", (seq,)).fetchone()
        event = self._row(row)
        self._check_event(event)
        return event

    def _prior_op(
        self, db: sqlite3.Connection, op_id: str, kind: str, actor: str, payload: dict[str, Any]
    ) -> int | None:
        row = db.execute("SELECT seq, kind, actor, payload_sha FROM events WHERE op_id=?", (op_id,)).fetchone()
        if row is None:
            return None
        if (row[1], row[2], row[3]) != (kind, actor, sha256_hex(canonicalize(payload))):
            raise IdempotencyConflict(f"op_id {op_id!r} already committed as seq {row[0]} with different content")
        return int(row[0])

    def find_op(self, op_id: str) -> Event | None:
        row = self._db.execute("SELECT * FROM events WHERE op_id=?", (op_id,)).fetchone()
        return None if row is None else self._row(row)

    def check_fence(self, db: sqlite3.Connection, resource: str, token: int) -> None:
        row = db.execute("SELECT token, expires_ms FROM leases WHERE resource=?", (resource,)).fetchone()
        if row is None or row[0] != token or row[1] <= self.now():
            raise StaleFence(f"fence {resource}#{token} is not the live lease")

    def append_locked(
        self, db: sqlite3.Connection, kind: str, actor: str, payload: dict[str, Any], op_id: str | None = None
    ) -> int:
        """Append inside an open :meth:`transaction`. Returns the new seq."""
        body = canonicalize(payload)
        payload_sha = sha256_hex(body)
        head = db.execute("SELECT seq, hash, hlc FROM events ORDER BY seq DESC LIMIT 1").fetchone()
        seq = 1 if head is None else head[0] + 1
        prev = GENESIS_ROOT if head is None else head[1]
        last_stamp = None if head is None else HLCStamp.decode(head[2])
        hlc = self.clock.tick(last_stamp).encode()
        event_id = uuid.uuid4().hex
        digest = sha256_hex(_header(seq, event_id, hlc, kind, actor, payload_sha, prev, op_id))
        signer_id = signature = None
        if self.signer is not None:
            signer_id, signature = self.signer.key_id, self.signer.sign(bytes.fromhex(digest))
        db.execute(
            "INSERT INTO events(seq,event_id,hlc,kind,actor,payload,payload_sha,prev_hash,hash,signer,signature,op_id)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (seq, event_id, hlc, kind, actor, body, payload_sha, prev, digest, signer_id, signature, op_id),
        )
        return int(seq)

    def _post_write_fetch(self, seq: int) -> Event:
        event = self.get(seq)
        if event is None:
            raise LedgerError(f"post-write fetch: seq {seq} missing after commit")
        self._check_event(event)
        return event

    # -- reads --------------------------------------------------------------------

    def get(self, seq: int) -> Event | None:
        row = self._db.execute("SELECT * FROM events WHERE seq=?", (seq,)).fetchone()
        return None if row is None else self._row(row)

    def head(self) -> Event | None:
        row = self._db.execute("SELECT * FROM events ORDER BY seq DESC LIMIT 1").fetchone()
        return None if row is None else self._row(row)

    def events(self, after: int = 0, kind: str | None = None) -> Iterator[Event]:
        if kind is None:
            cur = self._db.execute("SELECT * FROM events WHERE seq>? ORDER BY seq", (after,))
        else:
            cur = self._db.execute("SELECT * FROM events WHERE seq>? AND kind=? ORDER BY seq", (after, kind))
        for row in cur:
            yield self._row(row)

    @staticmethod
    def _row(row: tuple[Any, ...]) -> Event:
        seq, event_id, hlc, kind, actor, body, payload_sha, prev, digest, signer, signature, op_id = row
        return Event(
            seq, event_id, hlc, kind, actor, json.loads(body), payload_sha, prev, digest, signer, signature, op_id
        )

    # -- verification ---------------------------------------------------------------

    def public_keys(self) -> dict[str, str]:
        return dict(self._db.execute("SELECT key_id, public_hex FROM signers"))

    def _check_event(self, event: Event, keys: dict[str, str] | None = None) -> None:
        body = canonicalize(event.payload)
        if sha256_hex(body) != event.payload_sha:
            raise ChainBroken(f"seq {event.seq}: payload digest mismatch")
        stored = self._db.execute("SELECT payload FROM events WHERE seq=?", (event.seq,)).fetchone()[0]
        if sha256_hex(bytes(stored)) != event.payload_sha:
            raise ChainBroken(f"seq {event.seq}: stored payload bytes do not match digest")
        header = _header(
            event.seq,
            event.event_id,
            event.hlc,
            event.kind,
            event.actor,
            event.payload_sha,
            event.prev_hash,
            event.op_id,
        )
        if sha256_hex(header) != event.hash:
            raise ChainBroken(f"seq {event.seq}: header hash mismatch")
        if event.signer is not None:
            keys = keys if keys is not None else self.public_keys()
            public_hex = keys.get(event.signer)
            if public_hex is None:
                raise ChainBroken(f"seq {event.seq}: unknown signer {event.signer}")
            signed = event.signature is not None and verify(
                public_from_hex(public_hex), bytes.fromhex(event.hash), event.signature
            )
            if not signed:
                raise ChainBroken(f"seq {event.seq}: bad signature")

    def verify_chain(self, require_signatures: bool = False) -> int:
        """Re-derive the whole chain. Returns the number of events verified."""
        keys = self.public_keys()
        prev_hash, prev_stamp, count = GENESIS_ROOT, None, 0
        for event in self.events():
            count += 1
            if event.seq != count:
                raise ChainBroken(f"gap: expected seq {count}, found {event.seq}")
            if event.prev_hash != prev_hash:
                raise ChainBroken(f"seq {event.seq}: prev_hash does not link to seq {event.seq - 1}")
            stamp = HLCStamp.decode(event.hlc)
            if prev_stamp and (stamp.wall_ms, stamp.counter) <= (prev_stamp.wall_ms, prev_stamp.counter):
                raise ChainBroken(f"seq {event.seq}: HLC not strictly increasing")
            if require_signatures and event.signer is None:
                raise ChainBroken(f"seq {event.seq}: unsigned event in a signed hive")
            self._check_event(event, keys)
            prev_hash, prev_stamp = event.hash, stamp
        return count
