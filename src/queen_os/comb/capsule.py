"""Bounded, derived task context. A capsule is never a capability or an action replay."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from queen_os.comb.ledger import Event, LedgerError
from queen_os.comb.projection import EggView, fold_events
from queen_os.hive import Hive
from queen_os.queen.egg import TaskEgg, load
from queen_os.serial.afser import sha256_hex
from queen_os.serial.jcs import canonicalize

MAX_CAPSULE_BYTES = 32_768
MAX_EVENTS = 4096
MAX_EVENT_BYTES = 65_536
MAX_HISTORY_BYTES = 2 * 1024 * 1024
MAX_DEPENDENCIES = 32
MAX_DEPTH = 8
MAX_PARENTS = 16
MAX_BLOB_BYTES = 65_536
MAX_ATTEMPTS = 16
_EGG = re.compile(r"egg_[0-9a-f]{32}")
_SHA = re.compile(r"[0-9a-f]{64}")


class CapsuleError(ValueError):
    """Missing, inconsistent, unsupported or over-budget context; never silently trimmed."""


class StaleCapsule(CapsuleError):
    """The authoritative head no longer matches. Rebuild rather than trusting cached state."""


@dataclass(frozen=True)
class ResumeCapsule:
    raw: bytes

    @property
    def sha256(self) -> str:
        return sha256_hex(self.raw)

    @property
    def payload(self) -> dict[str, Any]:
        return dict(json.loads(self.raw))  # fresh copy, never a mutable authority cache


def _json(raw: bytes) -> Any:
    value = json.loads(raw.decode("utf-8"))
    if canonicalize(value) != raw:
        raise CapsuleError("noncanonical or ambiguous JSON")
    return value


def _read(root: Path, path: Path, expected: str) -> bytes:
    if not isinstance(expected, str) or _SHA.fullmatch(expected) is None or path.is_symlink():
        raise CapsuleError("invalid digest or symlinked context file")
    # Inspect every component below the source root, including shard/enclave directories.
    relative = path.relative_to(root)
    if any((root / parent).is_symlink() for parent in relative.parents):
        raise CapsuleError("symlinked context directory")
    with path.open("rb") as stream:
        raw = stream.read(MAX_BLOB_BYTES + 1)
    if len(raw) > MAX_BLOB_BYTES or sha256_hex(raw) != expected:
        raise CapsuleError("context file exceeds bound or its digest differs")
    return raw


def _blob(hive: Hive, digest: str) -> None:
    if not isinstance(digest, str) or _SHA.fullmatch(digest) is None:
        raise CapsuleError("invalid context blob reference")
    _read(hive.root, hive.blobs.root / digest[:2] / digest, digest)


def _artifact(hive: Hive, view: EggView) -> dict[str, Any] | None:
    if view.state not in {"delivered", "hatched"}:
        return None  # rejected/quarantined output is deliberately not exported as context
    if view.artifact_sha is None:
        raise CapsuleError("delivered task has no artifact digest")
    enclave = "committed" if view.state == "hatched" else "staging"
    raw = _read(hive.root, hive.root / enclave / (view.egg_id + ".json"), view.artifact_sha)
    value = _json(raw)
    if not isinstance(value, dict) or set(value) != {"egg_id", "output"} or value["egg_id"] != view.egg_id:
        raise CapsuleError("artifact envelope differs from its task")
    return {"sha256": view.artifact_sha, "output": value["output"]}


def _event_ref(event: Event) -> dict[str, Any]:
    return {"seq": event.seq, "hash": event.hash}


def _bounded_head(hive: Hive) -> tuple[Event, list[Event]]:
    db = hive.ledger._db  # called only inside Ledger.read_snapshot
    count, largest, total = db.execute(
        "SELECT COUNT(*), COALESCE(MAX(LENGTH(payload)),0), COALESCE(SUM(LENGTH(payload)),0) FROM events"
    ).fetchone()
    if not 0 < count <= MAX_EVENTS or largest > MAX_EVENT_BYTES or total > MAX_HISTORY_BYTES:
        raise CapsuleError("ledger exceeds capsule verification bounds")
    if hive.ledger.verify_chain(require_signatures=True) != count:
        raise CapsuleError("ledger changed during snapshot")
    events = list(hive.ledger.events())
    genesis = events[0]
    if (
        genesis.kind != "hive.genesis"
        or genesis.payload.get("node_id") != hive.node_id
        or genesis.payload.get("mode") != hive.mode
        or genesis.signer != genesis.payload.get("host_key_id")
    ):
        raise CapsuleError("hive identity and signed genesis differ")
    return events[-1], events


def _build(hive: Hive, egg_id: str, max_bytes: int, at_seq: int | None = None) -> ResumeCapsule:
    if type(max_bytes) is not int or not 1 <= max_bytes <= MAX_CAPSULE_BYTES:
        raise CapsuleError("capsule byte budget must be an integer within the hard limit")
    if not isinstance(egg_id, str) or _EGG.fullmatch(egg_id) is None:
        raise CapsuleError("invalid task identifier")
    head, events = _bounded_head(hive)
    if at_seq is not None:
        if type(at_seq) is not int or not 1 <= at_seq <= len(events):
            raise CapsuleError("invalid historical head")
        events = events[:at_seq]
        head = events[-1]
    views = fold_events(events)
    eggs: dict[str, TaskEgg] = {}
    laid: dict[str, Event] = {}
    visiting: set[str] = set()
    heights: dict[str, int] = {}

    def visit(ident: str, depth: int) -> None:
        if depth > MAX_DEPTH or ident in visiting or _EGG.fullmatch(ident) is None:
            raise CapsuleError("dependency depth, identity or cycle violation")
        if ident in eggs:
            if depth + heights[ident] > MAX_DEPTH:
                raise CapsuleError("dependency depth exceeds bound on a shared path")
            return
        if len(eggs) + len(visiting) >= MAX_DEPENDENCIES + 1:
            raise CapsuleError("dependency count exceeds bound")
        visiting.add(ident)
        egg = load(hive, ident)
        records = [e for e in events if e.kind == "egg.laid" and e.payload.get("egg_id") == ident]
        if len(records) != 1 or canonicalize(egg.to_json()) != canonicalize(records[0].payload):
            raise CapsuleError("ambiguous task declaration")
        if len(egg.parents) > MAX_PARENTS or len(set(egg.parents)) != len(egg.parents):
            raise CapsuleError("parent count or duplicate parent violation")
        for parent in egg.parents:
            visit(parent, depth + 1)
            if laid[parent].seq >= records[0].seq:
                raise CapsuleError("parent was not declared before its child")
        visiting.remove(ident)
        eggs[ident], laid[ident] = egg, records[0]
        heights[ident] = max((1 + heights[parent] for parent in egg.parents), default=0)

    visit(egg_id, 0)
    egg, view = eggs[egg_id], views[egg_id]
    artifact = _artifact(hive, view)
    if (
        at_seq is None
        and view.state in {"laid", "claimed"}
        and any((hive.root / location / (egg_id + ".json")).exists() for location in ["staging", "committed"])
    ):
        raise CapsuleError("unrecorded artifact effect requires reconciliation")
    claims = [e for e in events if e.kind == "egg.claimed" and e.payload.get("egg_id") == egg_id]
    if len(claims) > MAX_ATTEMPTS:
        raise CapsuleError("claim history exceeds capsule attempt bound")
    if any(
        type(e.payload.get("lease_token")) is not int
        or e.payload["lease_token"] <= 0
        or not isinstance(e.payload.get("token_id"), str)
        for e in claims
    ):
        raise CapsuleError("invalid claim reference")
    token_ids = {e.payload["token_id"] for e in claims}
    spends = [e for e in events if e.kind == "capability.spent" and e.payload.get("token_id") in token_ids]
    receipts = [e for e in events if e.kind == "inference.receipt" and e.payload.get("token_id") in token_ids]
    if len(spends) > MAX_ATTEMPTS or len(receipts) > MAX_ATTEMPTS:
        raise CapsuleError("inference history exceeds capsule attempt bound")
    evidence = []
    for receipt in receipts:
        p = receipt.payload
        for name in ["request_sha", "response_sha"]:
            _blob(hive, p[name])
        if p.get("v") == 2:
            _blob(hive, p["structured_output"]["schema_sha"])
        evidence.append({**_event_ref(receipt), "token_id": p["token_id"], "provider_kind": p["provider_kind"]})
    resource = "egg:" + egg_id
    lease: dict[str, Any] | None = None
    for event in events:
        p = event.payload
        if p.get("resource") != resource or event.kind not in {"lease.granted", "lease.renewed", "lease.released"}:
            continue
        lease = {
            "holder": event.actor,
            "token": p["token"],
            "expires_ms": 0 if event.kind == "lease.released" else p["expires_ms"],
        }
    row = hive.ledger._db.execute(
        "SELECT holder, token, expires_ms FROM leases WHERE resource=?", (resource,)
    ).fetchone()
    actual = None if row is None else {"holder": row[0], "token": row[1], "expires_ms": row[2]}
    if at_seq is None and canonicalize(actual) != canonicalize(lease):
        raise CapsuleError("mutable lease view differs from signed history")
    last = claims[-1] if claims else None
    dependencies = []
    for ident in sorted(set(eggs) - {egg_id}):
        parent = views[ident]
        output = _artifact(hive, parent) if ident in egg.parents else None
        dependencies.append(
            {
                "egg_id": ident,
                "egg_sha256": sha256_hex(canonicalize(eggs[ident].to_json())),
                "laid": _event_ref(laid[ident]),
                "state": parent.state,
                "parents": list(eggs[ident].parents),
                "artifact_sha256": parent.artifact_sha,
                "direct_parent_output": output,
            }
        )
    step = {
        "laid": "claim_required",
        "claimed": "check_existing_claim",
        "delivered": "gate_review_required",
        "hatched": "complete",
        "purged": "quarantined",
    }[view.state]
    if (
        view.state == "claimed"
        and last is not None
        and any(e.payload["token_id"] == last.payload["token_id"] for e in spends)
    ):
        step = "reconcile_effect"  # even a missing response cannot authorize a repeated attempt
    body = {
        "v": 1,
        "kind": "queen.resume",
        "authority": "none",
        "hive": {"node_id": hive.node_id, "mode": hive.mode, "genesis_hash": events[0].hash},
        "head": _event_ref(head),
        "task": {
            "egg_id": egg_id,
            "goal_id": egg.goal_id,
            "state": view.state,
            "laid": _event_ref(laid[egg_id]),
            "egg_sha256": sha256_hex(canonicalize(egg.to_json())),
            "schema_sha256": sha256_hex(canonicalize(egg.schema)),
            "input": egg.input,
            "output_schema": egg.schema,
            "tools_requested": list(egg.tools),
            "artifact": artifact,
        },
        "dependencies": dependencies,
        "lease": lease,
        "last_claim": None
        if last is None
        else {
            **_event_ref(last),
            "actor": last.actor,
            "token_id": last.payload["token_id"],
            "lease_token": last.payload["lease_token"],
        },
        "spends": [{**_event_ref(e), "token_id": e.payload["token_id"]} for e in spends],
        "receipts": evidence,
        "next_step": step,
    }
    raw = canonicalize(body)
    if len(raw) > max_bytes:
        raise CapsuleError("capsule exceeds byte budget; split the work, never silently trim")
    return ResumeCapsule(raw)


def build_capsule(hive: Hive, egg_id: str, max_bytes: int = MAX_CAPSULE_BYTES) -> ResumeCapsule:
    """Read one signed snapshot; no event, capability, artifact or inference is created."""
    try:
        with hive.ledger.read_snapshot():
            return _build(hive, egg_id, max_bytes)
    except CapsuleError:
        raise
    except (OSError, KeyError, TypeError, ValueError, LedgerError, RecursionError) as exc:
        raise CapsuleError(f"cannot construct verified capsule: {type(exc).__name__}") from exc


def verify_capsule(hive: Hive, raw: bytes, max_bytes: int = MAX_CAPSULE_BYTES) -> ResumeCapsule:
    """Rebuild against the authoritative current snapshot; capsule fields grant nothing."""
    try:
        if not isinstance(raw, bytes) or len(raw) > MAX_CAPSULE_BYTES:
            raise CapsuleError("capsule encoding or size limit")
        value = _json(raw)
        if not isinstance(value, dict) or type(value.get("v")) is not int or value["v"] != 1:
            raise CapsuleError("unknown capsule version")
        with hive.ledger.read_snapshot():
            head = hive.ledger.head()
            if head is None or canonicalize(value.get("head")) != canonicalize(_event_ref(head)):
                raise StaleCapsule("capsule head differs; rebuild current context")
            expected = _build(hive, value["task"]["egg_id"], max_bytes)
            if expected.raw != raw:
                raise CapsuleError("capsule differs from verified state")
            return expected
    except StaleCapsule:
        raise
    except CapsuleError:
        raise
    except (OSError, KeyError, TypeError, ValueError, LedgerError, RecursionError) as exc:
        raise CapsuleError(f"cannot verify capsule: {type(exc).__name__}") from exc


def _verify_recorded(hive: Hive, raw: bytes) -> ResumeCapsule:
    """Historical readback inside the caller's verified snapshot/transaction."""
    if not isinstance(raw, bytes) or len(raw) > MAX_CAPSULE_BYTES:
        raise CapsuleError("capsule encoding or size limit")
    value = _json(raw)
    if not isinstance(value, dict) or type(value.get("v")) is not int or value["v"] != 1:
        raise CapsuleError("unknown capsule version")
    expected = _build(hive, value["task"]["egg_id"], MAX_CAPSULE_BYTES, value["head"]["seq"])
    if expected.raw != raw:
        raise CapsuleError("recorded capsule differs from verified prefix")
    return expected


def verify_recorded_capsule(hive: Hive, raw: bytes) -> ResumeCapsule:
    """Replay a historical prefix for provenance only; NEVER restores current authority.

    Current ledger signatures and bounded source files still verify. Later lease rows
    and later unrecorded artifacts cannot describe that old prefix; current resume
    retains its strict head/lease/artifact checks through verify_capsule instead.
    """
    try:
        with hive.ledger.read_snapshot():
            return _verify_recorded(hive, raw)
    except CapsuleError:
        raise
    except (OSError, KeyError, TypeError, ValueError, LedgerError, RecursionError) as exc:
        raise CapsuleError(f"cannot replay capsule: {type(exc).__name__}") from exc
