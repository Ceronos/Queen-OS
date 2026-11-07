"""Abrupt synthetic writer exit at controlled SQLite boundaries, not power loss."""

from __future__ import annotations

import multiprocessing as mp
import os
import sqlite3
from pathlib import Path
from typing import Any

import pytest

from queen_os.comb import HybridLogicalClock, Leases, Ledger
from queen_os.crypto import KeyRing


def open_ledger(root: Path) -> Ledger:
    keys = KeyRing(root / "vault")
    signer = keys.load("host") if keys.exists("host") else keys.create("host")
    return Ledger(root / "ledger.sqlite3", HybridLogicalClock("fixture_node"), signer, lambda: 1_000)


def _exit_writer(directory: str, phase: str) -> None:
    ledger = open_ledger(Path(directory))
    if phase == "before_commit":
        original = ledger.append_locked

        def exit_after_insert(db: sqlite3.Connection, kind: str, actor: str, payload: dict[str, Any]) -> int:
            original(db, kind, actor, payload)
            os._exit(17)  # bypass finally, connection close and Python cleanup

        ledger.append_locked = exit_after_insert
        Leases(ledger).acquire("fixture:task", "fixture_worker", ttl_ms=100)
    else:

        def exit_before_readback(seq: int) -> None:
            os._exit(23)  # append has COMMITted, but its caller has no acknowledgement

        ledger._post_write_fetch = exit_before_readback
        ledger.append(
            "fixture.effect", "fixture_worker", {"fixture": True, "operation_id": "synthetic-exit-001", "result": 91}
        )
    os._exit(99)  # reaching here means the intended failure boundary was not exercised


@pytest.mark.parametrize(("phase", "exitcode"), [("before_commit", 17), ("after_commit", 23)])
def test_abrupt_writer_exit_recovers_only_committed_effects(tmp_path: Path, phase: str, exitcode: int) -> None:
    with open_ledger(tmp_path) as ledger:
        ledger.append("fixture.started", "fixture_controller", {"fixture": True})
    writer = mp.get_context("spawn").Process(target=_exit_writer, args=(str(tmp_path), phase))
    writer.start()
    try:
        writer.join(30)
        assert not writer.is_alive(), "synthetic writer timed out"
        assert writer.exitcode == exitcode  # import/startup failures cannot count as evidence
    finally:
        if writer.is_alive():
            writer.terminate()
            writer.join(10)
        writer.close()

    with open_ledger(tmp_path) as recovered:
        if phase == "before_commit":
            assert recovered.verify_chain(require_signatures=True) == 1
            assert list(recovered.events(kind="lease.granted")) == []
            with sqlite3.connect(recovered.path) as raw:
                assert raw.execute("SELECT COUNT(*) FROM leases").fetchone()[0] == 0
            lease = Leases(recovered).acquire("fixture:task", "fixture_worker_new", ttl_ms=100)
            assert lease.token == 1
            recovered.append("fixture.done", "fixture_worker_new", {"fixture": True}, fence=lease.fence)
        else:
            assert recovered.verify_chain(require_signatures=True) == 2
            effects = list(recovered.events(kind="fixture.effect"))
            assert len(effects) == 1
            assert effects[0].payload == {"fixture": True, "operation_id": "synthetic-exit-001", "result": 91}
            recovered.append(
                "fixture.reconciled", "fixture_controller", {"fixture": True, "event_id": effects[0].event_id}
            )
            assert len(list(recovered.events(kind="fixture.effect"))) == 1
        assert recovered.verify_chain(require_signatures=True) == 3
