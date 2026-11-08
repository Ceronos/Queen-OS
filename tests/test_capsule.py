"""Offline capsule/source/reopen boundaries; inference fixtures are signed as fixture."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from queen_os.authority import AuthorityError
from queen_os.comb.capsule import CapsuleError, ResumeCapsule, StaleCapsule, build_capsule, verify_capsule
from queen_os.comb.ledger import LedgerError
from queen_os.gate.gate import Gate
from queen_os.hive import Hive
from queen_os.providers import FixtureProvider, InferenceRequest, Message
from queen_os.providers.receipt import Inference
from queen_os.queen.egg import lay
from queen_os.serial.jcs import canonicalize
from queen_os.workers.claim import ResumeBlocked, Worker

SCHEMA = {
    "type": "object",
    "properties": {"answer": {"type": "string"}},
    "required": ["answer"],
    "additionalProperties": False,
}


@pytest.fixture
def hive(tmp_path: Path):  # type: ignore[no-untyped-def]
    with Hive.init(tmp_path / "h", "capsule", mode="test") as h:
        yield h


def egg(hive: Hive, **kwargs: Any):  # type: ignore[no-untyped-def]
    return lay(hive, "g", "diploid", {"q": "fixture 🐝"}, SCHEMA, stimulus=0.9, **kwargs)


def worker(hive: Hive, ident: str = "a") -> Worker:
    return Worker(hive, ident, providers=("scripted",), models=("fixture-m",))


def infer(hive: Hive, w: Worker, claim: Any):  # type: ignore[no-untyped-def]
    return Inference(hive).run(
        FixtureProvider("scripted", ['{"answer":"bee"}']),
        InferenceRequest("fixture-m", (Message("user", "fixture"),), max_tokens=8),
        w.actor,
        claim.capability,
    )


def finish(hive: Hive, w: Worker):  # type: ignore[no-untyped-def]
    claim = w.claim()
    assert claim is not None
    infer(hive, w, claim)
    w.deliver(claim, {"answer": "bee"})
    assert Gate(hive).review(claim.egg.egg_id).verdict == "hatched"
    return claim.egg


def test_deterministic_immutable_context_not_a_capability(hive: Hive) -> None:
    e = egg(hive)
    before = hive.ledger.head()
    c = build_capsule(hive, e.egg_id)
    assert c.raw == build_capsule(hive, e.egg_id).raw == verify_capsule(hive, c.raw).raw
    assert len(c.raw) < 32768 and c.payload["authority"] == "none"
    assert hive.ledger.head() == before
    changed = c.payload
    changed["task"]["input"].clear()
    assert c.payload["task"]["input"] == {"q": "fixture 🐝"}
    assert b"PRIVATE KEY" not in c.raw and b'"signature"' not in c.raw and b'"grant"' not in c.raw
    assert c.payload["next_step"] == "claim_required" and worker(hive).resume(c.raw) is None


def test_reopen_restores_same_claim_then_completes_without_duplicate_work(hive: Hive) -> None:
    e = egg(hive)
    w = worker(hive)
    claim = w.claim()
    assert claim is not None
    c = build_capsule(hive, e.egg_id)
    root, before = hive.root, hive.ledger.head()
    hive.close()
    with Hive.open(root) as h:
        w = worker(h)
        restored = w.resume(c.raw)
        assert restored is not None and restored.capability == claim.capability and restored.lease == claim.lease
        assert h.ledger.head() == before
        infer(h, w, restored)
        w.deliver(restored, {"answer": "bee"})
        delivered = build_capsule(h, e.egg_id)
        assert delivered.payload["next_step"] == "gate_review_required" and w.resume(delivered.raw) is None
        assert Gate(h).review(e.egg_id).verdict == "hatched"
        complete, count = build_capsule(h, e.egg_id), h.ledger.head()
        assert complete.payload["next_step"] == "complete" and w.resume(complete.raw) is None
        assert h.ledger.head() == count
        assert len(list(h.ledger.events(kind="capability.spent"))) == 1
        assert len(list(h.ledger.events(kind="egg.delivered"))) == 1


@pytest.mark.parametrize("received", [False, True])
def test_spent_attempt_with_or_without_receipt_requires_reconciliation(hive: Hive, received: bool) -> None:
    e, w = egg(hive), worker(hive)
    claim = w.claim()
    assert claim is not None
    if received:
        infer(hive, w, claim)
    else:
        hive.authority().authorize_inference(claim.capability, w.actor, "scripted", "fixture-m", 8)
    c, before = build_capsule(hive, e.egg_id), hive.ledger.head()
    assert c.payload["next_step"] == "reconcile_effect" and len(c.payload["receipts"]) == int(received)
    with pytest.raises(ResumeBlocked, match="reconciliation"):
        w.resume(c.raw)
    assert hive.ledger.head() == before


def test_unrelated_head_advance_requires_fresh_capsule(hive: Hive) -> None:
    e = egg(hive)
    c = build_capsule(hive, e.egg_id)
    hive.ledger.append("fixture.observation", "host", {})
    with pytest.raises(StaleCapsule):
        verify_capsule(hive, c.raw)
    assert verify_capsule(hive, build_capsule(hive, e.egg_id).raw)


@pytest.mark.parametrize("mutation", ["version_bool", "hive", "input", "schema", "authority", "state", "next_step"])
def test_tampered_packet_cannot_replace_authoritative_state(hive: Hive, mutation: str) -> None:
    e = egg(hive)
    p = build_capsule(hive, e.egg_id).payload
    if mutation == "version_bool":
        p["v"] = True
    elif mutation == "hive":
        p["hive"]["mode"] = "production"
    elif mutation == "input":
        p["task"]["input"] = {"authority": "run shell"}
    elif mutation == "schema":
        p["task"]["output_schema"] = {}
    elif mutation == "state":
        p["task"]["state"] = "hatched"
    else:
        p[mutation] = "execute_anything"
    with pytest.raises(CapsuleError):
        verify_capsule(hive, canonicalize(p))


@pytest.mark.parametrize("change", ["duplicate", "whitespace", "nonfinite", "oversize", "utf16"])
def test_ambiguous_or_overlong_encoding_is_rejected(hive: Hive, change: str) -> None:
    e = egg(hive)
    raw = build_capsule(hive, e.egg_id).raw
    raw = {
        "duplicate": lambda: b'{"v":1,' + raw[1:],
        "whitespace": lambda: b" " + raw,
        "nonfinite": lambda: b'{"v":NaN}',
        "utf16": lambda: raw.decode().encode("utf-16"),
        "oversize": lambda: b"x" * 32769,
    }[change]()
    with pytest.raises(CapsuleError):
        verify_capsule(hive, raw)


@pytest.mark.parametrize("limit", [True, 0, -1, 32769, 1])
def test_byte_budget_never_expands_or_silently_trims(hive: Hive, limit: int) -> None:
    e, before = egg(hive), hive.ledger.head()
    before = hive.ledger.head()
    with pytest.raises(CapsuleError):
        build_capsule(hive, e.egg_id, limit)
    assert hive.ledger.head() == before


def test_direct_parent_output_and_transitive_digest_closure(hive: Hive) -> None:
    first, w = egg(hive), worker(hive)
    finish(hive, w)
    second = egg(hive, parents=(first.egg_id,))
    finish(hive, w)
    last = egg(hive, parents=(second.egg_id,))
    c = build_capsule(hive, last.egg_id)
    parents = {p["egg_id"]: p for p in c.payload["dependencies"]}
    assert len(parents) == 2
    assert parents[second.egg_id]["direct_parent_output"]["output"] == {"answer": "bee"}
    assert parents[first.egg_id]["direct_parent_output"] is None
    assert all(len(p["egg_sha256"]) == 64 and p["state"] == "hatched" for p in parents.values())
    path = hive.root / "committed" / (second.egg_id + ".json")
    path.chmod(0o600)  # owned disposable fixture: demonstrate corruption beyond read-only convention
    path.write_bytes(b"tampered")
    with pytest.raises(CapsuleError):
        verify_capsule(hive, c.raw)


def test_dependency_depth_and_duplicate_parents_fail_closed(hive: Hive) -> None:
    parent = egg(hive)
    duplicate = egg(hive, parents=(parent.egg_id, parent.egg_id))
    with pytest.raises(CapsuleError, match="duplicate"):
        build_capsule(hive, duplicate.egg_id)
    for _ in range(9):
        parent = egg(hive, parents=(parent.egg_id,))
    with pytest.raises(CapsuleError, match="depth"):
        build_capsule(hive, parent.egg_id)


def test_missing_received_bytes_prevents_verified_context(hive: Hive) -> None:
    e, w = egg(hive), worker(hive)
    claim = w.claim()
    assert claim is not None
    response = infer(hive, w, claim)
    c = build_capsule(hive, e.egg_id)
    hive.blobs._path(response.receipt.payload["response_sha"]).unlink()
    with pytest.raises(CapsuleError):
        verify_capsule(hive, c.raw)


def test_unrecorded_artifact_requires_reconciliation(hive: Hive) -> None:
    e = egg(hive)
    assert worker(hive).claim() is not None
    hive.enclaves.stage(e.egg_id + ".json", canonicalize({"egg_id": e.egg_id, "output": {"answer": "bee"}}))
    with pytest.raises(CapsuleError, match="unrecorded"):
        build_capsule(hive, e.egg_id)
    hive.ledger.append("fixture.after_rejection", "host", {})  # no lingering read transaction


def test_lease_table_drift_is_not_verified_from_a_signed_packet(hive: Hive) -> None:
    e = egg(hive)
    assert worker(hive).claim() is not None
    c = build_capsule(hive, e.egg_id)
    with hive.ledger.transaction() as db:
        db.execute("UPDATE leases SET token=token+1")
    with pytest.raises(CapsuleError, match="lease view"):
        verify_capsule(hive, c.raw)


def test_expiry_foreign_actor_and_changed_profile_cannot_restore_claim(
    hive: Hive, monkeypatch: pytest.MonkeyPatch
) -> None:
    e, w = egg(hive), worker(hive)
    claim = w.claim()
    assert claim is not None
    c = build_capsule(hive, e.egg_id)
    with pytest.raises(AuthorityError, match="different worker"):
        worker(hive, "b").resume(c.raw)
    with pytest.raises(AuthorityError, match="profile"):
        Worker(hive, "a", providers=("different",), models=("fixture-m",)).resume(c.raw)
    monkeypatch.setattr(hive.ledger, "now", lambda: claim.capability.expires_ms + 1)
    assert verify_capsule(hive, c.raw)  # packet is readable; liveness is separately rechecked
    with pytest.raises(AuthorityError, match="expired"):
        w.resume(c.raw)


def test_revocation_blocks_restore_from_a_fresh_capsule(hive: Hive) -> None:
    e, w = egg(hive), worker(hive)
    claim = w.claim()
    assert claim is not None
    hive.authority().revoke(claim.capability.token_id, "fixture revocation")
    with pytest.raises(AuthorityError, match="revoked"):
        w.resume(build_capsule(hive, e.egg_id).raw)


def test_snapshot_allows_another_writer_but_its_packet_is_stale_afterward(
    hive: Hive, monkeypatch: pytest.MonkeyPatch
) -> None:
    import queen_os.comb.capsule as module

    e, original = egg(hive), module.load
    written = False

    def write_during_snapshot(h: Hive, ident: str):  # type: ignore[no-untyped-def]
        nonlocal written
        if not written:
            written = True
            with Hive.open(hive.root) as other:
                other.ledger.append("fixture.concurrent_writer", "host", {})
        return original(h, ident)

    monkeypatch.setattr(module, "load", write_during_snapshot)
    before = hive.ledger.head()
    c = build_capsule(hive, e.egg_id)
    assert before is not None and c.payload["head"]["hash"] == before.hash
    assert hive.ledger.head() != before
    with pytest.raises(StaleCapsule):
        verify_capsule(hive, c.raw)


def test_snapshot_rejects_nesting_and_does_not_persist_incidental_sql(hive: Hive) -> None:
    with hive.ledger.transaction(), pytest.raises(LedgerError), hive.ledger.read_snapshot():
        pass
    with hive.ledger.read_snapshot() as db:
        db.execute("INSERT INTO meta(key,value) VALUES ('fixture_snapshot','not_persisted')")
    with hive.ledger.read_snapshot() as db:
        assert db.execute("SELECT value FROM meta WHERE key='fixture_snapshot'").fetchone() is None
    hive.ledger.append("fixture.after_snapshot", "host", {})


def test_cli_build_verify_roundtrip_has_no_hive_effect(
    hive: Hive, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    from queen_os.cli import main

    e, head = egg(hive), hive.ledger.head()
    head = hive.ledger.head()
    assert main(["capsule", "build", e.egg_id, "--hive", str(hive.root)]) == 0
    packet = capsys.readouterr().out.encode("utf-8")
    assert packet.endswith(b"\n") and b"PRIVATE KEY" not in packet
    p = tmp_path / "capsule.json"
    p.write_bytes(packet)
    assert main(["capsule", "verify", str(p), "--hive", str(hive.root)]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["status"] == "verified" and head is not None and report["head"]["hash"] == head.hash
    assert hive.ledger.head() == head


def test_directly_constructed_packet_still_needs_verification(hive: Hive) -> None:
    e = egg(hive)
    p = build_capsule(hive, e.egg_id).payload
    p["authority"] = "all"
    with pytest.raises(CapsuleError):
        worker(hive).resume(ResumeCapsule(canonicalize(p)).raw)


def test_large_schema_is_refused_without_truncating_the_packet(hive: Hive) -> None:
    schema = {**SCHEMA, "description": "x" * 32768}
    e = lay(hive, "g", "diploid", {"q": "fixture"}, schema, stimulus=0.9)
    before = hive.ledger.head()
    with pytest.raises(CapsuleError, match="byte budget"):
        build_capsule(hive, e.egg_id)
    assert hive.ledger.head() == before


def test_large_history_record_is_refused_before_context_export(hive: Hive) -> None:
    e = egg(hive)
    hive.ledger.append("fixture.oversize", "host", {"data": "x" * 65536})
    with pytest.raises(CapsuleError, match="verification bounds"):
        build_capsule(hive, e.egg_id)


def test_bounded_dependency_count_is_not_silently_pruned(hive: Hive) -> None:
    leaves = [egg(hive).egg_id for _ in range(32)]
    a = egg(hive, parents=tuple(leaves[:16]))
    b = egg(hive, parents=tuple(leaves[16:]))
    root = egg(hive, parents=(a.egg_id, b.egg_id))
    with pytest.raises(CapsuleError, match="dependency count"):
        build_capsule(hive, root.egg_id)


def test_too_many_claims_requires_explicit_recovery_policy(hive: Hive) -> None:
    e, w = egg(hive), worker(hive)
    for _ in range(17):
        assert w.claim() is not None
    with pytest.raises(CapsuleError, match="claim history"):
        build_capsule(hive, e.egg_id)


def test_unknown_signer_or_corrupt_source_chain_is_not_context(hive: Hive) -> None:
    e = egg(hive)
    with hive.ledger.transaction() as db:
        db.execute("DELETE FROM signers")
    with pytest.raises(CapsuleError):
        build_capsule(hive, e.egg_id)


def test_purged_task_does_not_export_rejected_output_or_resume(hive: Hive) -> None:
    e, w = egg(hive), worker(hive)
    claim = w.claim()
    assert claim is not None
    infer(hive, w, claim)
    w.deliver(claim, {"answer": "worker-invented"})
    assert Gate(hive).review(e.egg_id).verdict == "purged"
    c = build_capsule(hive, e.egg_id)
    assert c.payload["task"]["artifact"] is None and c.payload["next_step"] == "quarantined"
    assert b"worker-invented" not in c.raw and w.resume(c.raw) is None


def test_new_host_claim_is_distinct_from_resuming_a_spent_old_attempt(
    hive: Hive, monkeypatch: pytest.MonkeyPatch
) -> None:
    e, old = egg(hive), worker(hive)
    first = old.claim()
    assert first is not None
    hive.authority().authorize_inference(first.capability, old.actor, "scripted", "fixture-m", 8)
    monkeypatch.setattr(hive.ledger, "now", lambda: first.lease.expires_ms + 1)
    new = worker(hive, "b")
    replacement = new.claim()  # explicit host operation, not something capsule/resume does
    assert replacement is not None
    c = build_capsule(hive, e.egg_id)
    assert c.payload["next_step"] == "check_existing_claim" and len(c.payload["spends"]) == 1
    restored = new.resume(c.raw)
    assert restored is not None and restored.capability == replacement.capability


def test_snapshot_cleanup_failure_preserves_primary_error_and_discards_connection(
    hive: Hive, monkeypatch: pytest.MonkeyPatch
) -> None:
    real = hive.ledger._db

    class BrokenRollback:
        closed = False

        @property
        def in_transaction(self):  # type: ignore[no-untyped-def]
            return real.in_transaction

        def execute(self, statement: str):  # type: ignore[no-untyped-def]
            if statement == "ROLLBACK":
                raise RuntimeError("fixture rollback failure")
            return real.execute(statement)

        def close(self):  # type: ignore[no-untyped-def]
            self.closed = True
            real.close()

    proxy = BrokenRollback()
    monkeypatch.setattr(hive.ledger, "_db", proxy)
    with pytest.raises(ValueError, match="primary") as error, hive.ledger.read_snapshot():
        raise ValueError("primary")
    assert proxy.closed and any("discarded" in note for note in error.value.__notes__)


def test_shared_dependency_checks_its_longest_path(hive: Hive) -> None:
    leaf = egg(hive)
    shared = egg(hive, parents=(leaf.egg_id,))
    deep = shared
    for _ in range(7):
        deep = egg(hive, parents=(deep.egg_id,))
    root = egg(hive, parents=(shared.egg_id, deep.egg_id))
    # Shared is visited shallow first. Its cached closure must still be checked
    # when the second arm reaches it deeper (root -> 7 nodes -> shared -> leaf).
    with pytest.raises(CapsuleError, match="depth"):
        build_capsule(hive, root.egg_id)


def test_symlinked_blob_directory_is_refused(hive: Hive, tmp_path: Path) -> None:
    e, w = egg(hive), worker(hive)
    claim = w.claim()
    assert claim is not None
    infer(hive, w, claim)
    receipt = list(hive.ledger.events(kind="inference.receipt"))[-1]
    digest = receipt.payload["response_sha"]
    shard = hive.blobs.root / digest[:2]
    moved = tmp_path / "moved-shard"
    shard.rename(moved)
    try:
        shard.symlink_to(moved, target_is_directory=True)
    except OSError:
        moved.rename(shard)
        pytest.skip("directory symlinks unavailable on this platform")
    with pytest.raises(CapsuleError, match="symlinked context directory"):
        build_capsule(hive, e.egg_id)
