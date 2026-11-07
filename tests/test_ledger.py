from __future__ import annotations

import multiprocessing as mp
import sqlite3
from pathlib import Path

import pytest

from queen_os.comb import GENESIS_ROOT, ChainBroken, HybridLogicalClock, LeaseHeld, Leases, Ledger, StaleFence
from queen_os.crypto import KeyRing


def make(tmp_path: Path, wall=None, signed: bool = True) -> Ledger:
    signer = KeyRing(tmp_path / "vault").create("host") if signed else None
    return Ledger(tmp_path / "ledger.sqlite3", HybridLogicalClock("n1", wall), signer, wall or (lambda: 1_000))


def test_chain_links_from_genesis_and_verifies(tmp_path: Path) -> None:
    with make(tmp_path) as led:
        e1 = led.append("egg.laid", "queen", {"egg": 1})
        e2 = led.append("egg.laid", "queen", {"egg": 2, "x": 0.5})
        assert e1.prev_hash == GENESIS_ROOT and e2.prev_hash == e1.hash
        assert led.verify_chain(require_signatures=True) == 2


@pytest.mark.parametrize(
    "sql",
    [
        "UPDATE events SET payload = CAST('{\"egg\":99}' AS BLOB) WHERE seq=1",
        "UPDATE events SET kind='egg.forged' WHERE seq=1",
        "UPDATE events SET prev_hash='GENESIS_ROOT_FFFFFFFFFFFFFFFF' WHERE seq=1",
        "UPDATE events SET signature=? WHERE seq=2",
        "DELETE FROM events WHERE seq=2",
        "UPDATE events SET hlc='000000000000001-00000000-n1' WHERE seq=3",
    ],
)
def test_any_tamper_breaks_the_chain(tmp_path: Path, sql: str) -> None:
    with make(tmp_path) as led:
        for i in range(3):
            led.append("egg.laid", "queen", {"egg": i})
    raw = sqlite3.connect(tmp_path / "ledger.sqlite3")
    raw.execute(sql, ("00" * 64,) if "?" in sql else ())
    raw.commit()
    raw.close()
    with make_reopen(tmp_path) as led, pytest.raises(ChainBroken):
        led.verify_chain(require_signatures=True)


def make_reopen(tmp_path: Path) -> Ledger:
    return Ledger(tmp_path / "ledger.sqlite3", HybridLogicalClock("n1"), None)


def test_rewriting_history_consistently_is_still_caught_by_signatures(tmp_path: Path) -> None:
    """An attacker who recomputes every hash without the host key still fails verification."""
    with make(tmp_path) as led:
        led.append("egg.laid", "queen", {"egg": 1})
    forger = Ledger(tmp_path / "forged.sqlite3", HybridLogicalClock("n1"), KeyRing(tmp_path / "evil").create("host"))
    forger.append("egg.laid", "queen", {"egg": 1})
    forger.close()
    raw = sqlite3.connect(tmp_path / "ledger.sqlite3")
    raw.execute("ATTACH ? AS f", (str(tmp_path / "forged.sqlite3"),))
    raw.execute("DELETE FROM main.events")
    raw.execute("INSERT INTO main.events SELECT * FROM f.events")
    raw.commit()
    raw.close()
    with make_reopen(tmp_path) as led, pytest.raises(ChainBroken, match="unknown signer"):
        led.verify_chain()


def test_hlc_stays_monotonic_when_wall_clock_regresses(tmp_path: Path) -> None:
    times = iter([5_000, 5_000, 4_000, 3_000, 6_000])
    with make(tmp_path, wall=lambda: next(times), signed=False) as led:
        for i in range(5):
            led.append("tick", "w", {"i": i})
        stamps = [e.hlc for e in led.events()]
        assert stamps == sorted(stamps) and len(set(stamps)) == 5
        assert led.verify_chain() == 5


def _hammer(path: str, worker: int, n: int) -> None:
    led = Ledger(Path(path), HybridLogicalClock(f"w{worker}"), None)
    for i in range(n):
        led.append("work.done", f"worker:{worker}", {"w": worker, "i": i})
    led.close()


def test_concurrent_processes_cannot_fork_the_chain(tmp_path: Path) -> None:
    db = tmp_path / "ledger.sqlite3"
    Ledger(db, HybridLogicalClock("init"), None).close()
    ctx = mp.get_context("spawn")
    procs = [ctx.Process(target=_hammer, args=(str(db), w, 25)) for w in range(4)]
    for p in procs:
        p.start()
    for p in procs:
        p.join(120)
        assert p.exitcode == 0
    with make_reopen(tmp_path) as led:
        assert led.verify_chain() == 100


# -- leases & fencing ------------------------------------------------------------


class Clock:
    def __init__(self) -> None:
        self.t = 1_000

    def __call__(self) -> int:
        return self.t


def test_lease_exclusion_expiry_and_fencing(tmp_path: Path) -> None:
    clock = Clock()
    with make(tmp_path, wall=clock) as led:
        leases = Leases(led)
        a = leases.acquire("egg:1", "worker:a", ttl_ms=500)
        assert a.token == 1
        with pytest.raises(LeaseHeld):
            leases.acquire("egg:1", "worker:b", ttl_ms=500)
        led.append("egg.progress", "worker:a", {"pct": 50}, fence=a.fence)

        clock.t += 600  # worker:a stalls past its lease
        b = leases.acquire("egg:1", "worker:b", ttl_ms=500)
        assert b.token == 2
        with pytest.raises(StaleFence):  # Two-arm: the zombie holder must be rejected
            led.append("egg.done", "worker:a", {"result": "late"}, fence=a.fence)
        led.append("egg.done", "worker:b", {"result": "ok"}, fence=b.fence)

        b2 = leases.renew(b, ttl_ms=1_000)
        assert b2.token == b.token and b2.expires_ms > b.expires_ms
        leases.release(b2)
        with pytest.raises(StaleFence):
            led.append("egg.done", "worker:b", {}, fence=b2.fence)
        assert [e.kind for e in led.events()].count("lease.granted") == 2
        assert led.verify_chain(require_signatures=True) == 5
