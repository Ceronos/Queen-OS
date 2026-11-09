"""Page-Robinson stimulus-response claiming (Thesis §5.3) over the comb.

A worker never receives work from another agent. It reads the ledger fold, picks ready eggs
whose stimulus clears its response threshold, and claims one by winning its lease.

    P(respond) = s² / (s² + θ²)      s = egg stimulus, θ = worker threshold

The deterministic form claims only eggs with P ≥ ½ (i.e. s ≥ θ), highest P first, ties broken
by laying order, so the same ledger always yields the same choice.

A claim is three things written together:
  1. lease ``egg:<id>`` (fencing token t)
  2. a capability whose **subject is exactly this worker**, scoped to this egg, with the egg's tools
     and the valve's budget, expiring no later than the lease (QOS-0020)
  3. ``egg.claimed`` with op_id ``egg.claimed:<id>:<t>``, fenced by the lease

Delivery validates the output against the egg's JSON Schema **before** anything is staged,
writes the canonical artifact into ``staging/`` with post-write fetch, appends a fenced
``egg.delivered`` (op_id ``egg.delivered:<id>``: one delivery per egg), and releases the lease.
Promotion to ``committed/`` belongs to the VerificationGate, not to the worker.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

import jsonschema

from queen_os.authority.tokens import ISSUED, REVOKED, AuthorityError, Capability, Grant
from queen_os.comb.capsule import StaleCapsule, verify_capsule
from queen_os.comb.leases import Lease, LeaseHeld
from queen_os.comb.projection import EggView, fold_eggs, ready
from queen_os.crypto.keys import public_from_hex, verify
from queen_os.hive import Hive
from queen_os.queen.egg import TaskEgg, load
from queen_os.queen.valve import Profile, ValveRefusal, profile_for
from queen_os.serial.jcs import canonicalize

_WORKER_RE = re.compile(r"^[a-z0-9][a-z0-9_.-]{0,62}$")


class OutputRejected(ValueError):
    """The worker's output violates the egg's schema. Nothing was staged."""


class ResumeBlocked(ValueError):
    """A spent or incomplete effect must be reconciled, not automatically executed again."""


@dataclass(frozen=True)
class Claim:
    egg: TaskEgg
    lease: Lease
    capability: Capability
    profile: Profile


def response(stimulus: float, threshold: float) -> float:
    if stimulus <= 0:
        return 0.0
    return stimulus**2 / (stimulus**2 + threshold**2)


class Worker:
    def __init__(
        self,
        hive: Hive,
        worker_id: str,
        *,
        threshold: float = 0.5,
        providers: tuple[str, ...] = ("*",),
        models: tuple[str, ...] = ("*",),
        goal_id: str | None = None,
    ) -> None:
        if not _WORKER_RE.match(worker_id):
            raise ValueError(f"worker id {worker_id!r} must match {_WORKER_RE.pattern}")
        if not 0.0 < threshold <= 1.0:
            raise ValueError("threshold must be in (0, 1]")
        if goal_id is not None and (
            not isinstance(goal_id, str) or re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,63}", goal_id) is None
        ):
            raise ValueError("invalid goal filter")
        self.goal_id = goal_id
        self.hive = hive
        self.actor = f"worker:{worker_id}"
        self.threshold = threshold
        self.providers = providers
        self.models = models

    # -- choosing ------------------------------------------------------------------

    def candidates(self) -> list[EggView]:
        eggs = [
            e
            for e in ready(fold_eggs(self.hive.ledger))
            if (self.goal_id is None or e.goal_id == self.goal_id) and response(e.stimulus, self.threshold) >= 0.5
        ]
        return sorted(eggs, key=lambda e: (-response(e.stimulus, self.threshold), e.laid_seq))

    # -- claiming ------------------------------------------------------------------

    def claim(self, ttl_ms: int = 60_000) -> Claim | None:
        for view in self.candidates():
            egg = load(self.hive, view.egg_id)  # re-verifies the Dufour signature
            try:
                profile = profile_for(egg)
            except ValveRefusal as exc:
                self._purge_refused(egg, str(exc))
                continue
            try:
                lease = self.hive.leases.acquire(f"egg:{egg.egg_id}", self.actor, ttl_ms)
            except LeaseHeld:
                continue  # another worker holds it; steal the next one
            return self._bind(egg, lease, profile)
        return None

    def _bind(self, egg: TaskEgg, lease: Lease, profile: Profile) -> Claim:
        grant = Grant(
            tools=egg.tools,
            providers=self.providers,
            models=self.models,
            max_output_tokens=profile.max_output_tokens,
            max_calls=profile.max_calls,
        )
        ttl = lease.expires_ms - self.hive.ledger.now()
        cap = self.hive.authority().issue(
            self.actor, f"egg:{egg.egg_id}", grant, ttl_ms=max(ttl, 1), not_after_ms=lease.expires_ms
        )
        self.hive.ledger.append(
            "egg.claimed",
            self.actor,
            {
                "egg_id": egg.egg_id,
                "lease_token": lease.token,
                "token_id": cap.token_id,
                "profile": {
                    "escalated": profile.escalated,
                    "ploidy": profile.ploidy,
                    "quorum": profile.quorum,
                    "risk": profile.risk,
                    "temperature": profile.temperature,
                },
            },
            fence=lease.fence,
            op_id=f"egg.claimed:{egg.egg_id}:{lease.token}",
        )
        return Claim(egg, lease, cap, profile)

    def _purge_refused(self, egg: TaskEgg, reason: str) -> None:
        self.hive.ledger.append(
            "egg.purged",
            self.actor,
            {"egg_id": egg.egg_id, "reason": "valve_refusal", "detail": reason},
            op_id=f"egg.purged:{egg.egg_id}",
        )

    def resume(self, capsule: bytes) -> Claim | None:
        """Restore only a current-head, live, unspent claim. Never mint or execute."""
        context = verify_capsule(self.hive, capsule).payload
        if context["task"]["state"] != "claimed":
            return None
        return self._restore_claim(context["task"]["egg_id"], expected_head=context["head"]["hash"])

    def recover_receipt(self, egg_id: str, receipt_seq: int) -> Claim | None:
        """Restore an existing live claim for delivery of ONE established response.

        No new capability, lease, inference or refund. The exact unique v2 receipt
        must bind this actor/current claim/schema. An uncertain spend cannot restore.
        Historical capsules are never accepted as current authority here.
        """
        return self._restore_claim(egg_id, receipt_seq=receipt_seq)

    def _restore_claim(
        self, egg_id: str, *, expected_head: str | None = None, receipt_seq: int | None = None
    ) -> Claim | None:
        from queen_os.providers.receipt import verify_receipt
        from queen_os.providers.structured import JsonSchemaOutput

        with self.hive.ledger.read_snapshot() as db:
            self.hive.ledger.verify_chain(require_signatures=True)
            head = self.hive.ledger.head()
            if expected_head is not None and (head is None or head.hash != expected_head):
                raise StaleCapsule("state moved during resume; rebuild")
            egg = load(self.hive, egg_id)
            if self.goal_id is not None and egg.goal_id != self.goal_id:
                raise ResumeBlocked("task is outside the selected goal")
            views = fold_eggs(self.hive.ledger)
            if views[egg_id].state != "claimed":
                return None
            if any(views[p].state != "hatched" for p in egg.parents):
                raise ResumeBlocked("parent work is not complete")
            claims = [e for e in self.hive.ledger.events(kind="egg.claimed") if e.payload["egg_id"] == egg_id]
            if not claims or claims[-1].actor != self.actor:
                raise AuthorityError("claim belongs to a different worker")
            last = claims[-1].payload
            issue = self.hive.ledger.find_op(f"{ISSUED}:{last['token_id']}")
            if issue is None:
                raise ResumeBlocked("claim has no issued capability")
            cap = Capability.from_json(issue.payload)
            profile = profile_for(egg)
            expected = Grant(egg.tools, self.providers, self.models, profile.max_output_tokens, profile.max_calls)
            if (
                cap.subject != self.actor
                or canonicalize(cap.to_json()) != canonicalize(issue.payload)
                or cap.scope != f"egg:{egg_id}"
                or canonicalize(cap.grant.to_json()) != canonicalize(expected.to_json())
            ):
                raise AuthorityError("claim capability differs from current worker/task profile")
            public = self.hive.ledger.public_keys().get(cap.issuer)
            if public is None or not verify(public_from_hex(public), canonicalize(cap.body()), cap.signature):
                raise AuthorityError("claim capability signature does not verify")
            if self.hive.ledger.find_op(f"{REVOKED}:{cap.token_id}") is not None:
                raise AuthorityError("claim capability is revoked")
            if not cap.not_before_ms <= self.hive.ledger.now() < cap.expires_ms:
                raise AuthorityError("claim capability has expired or is not yet valid")
            spends = [
                e for e in self.hive.ledger.events(kind="capability.spent") if e.payload.get("token_id") == cap.token_id
            ]
            if receipt_seq is None:
                if spends:
                    raise ResumeBlocked("prior inference attempt requires evidence reconciliation")
            else:
                receipts = [
                    e
                    for e in self.hive.ledger.events(kind="inference.receipt")
                    if e.payload.get("token_id") == cap.token_id
                ]
                if len(spends) != 1 or len(receipts) != 1 or receipts[0].seq != receipt_seq:
                    raise ResumeBlocked("one exact spend/receipt is required; ambiguous or missing evidence")
                receipt = receipts[0]
                verify_receipt(self.hive, receipt)
                if (
                    receipt.actor != self.actor
                    or spends[0].actor != self.actor
                    or receipt.payload.get("v") != 2
                    or receipt.payload["structured_output"]["schema_sha"] != JsonSchemaOutput(egg.schema).sha256
                ):
                    raise ResumeBlocked("receipt actor/schema differs from current claim")
            row = db.execute(
                "SELECT holder,token,expires_ms FROM leases WHERE resource=?", (f"egg:{egg_id}",)
            ).fetchone()
            history = [
                e
                for e in self.hive.ledger.events()
                if e.payload.get("resource") == f"egg:{egg_id}"
                and e.kind in {"lease.granted", "lease.renewed", "lease.released"}
            ]
            signed = None if not history else history[-1]
            if (
                row is None
                or signed is None
                or row[0] != self.actor
                or row[1] != last["lease_token"]
                or signed.actor != row[0]
                or signed.payload["token"] != row[1]
                or row[2] != (0 if signed.kind == "lease.released" else signed.payload["expires_ms"])
                or row[2] <= self.hive.ledger.now()
                or cap.expires_ms > row[2]
            ):
                raise ResumeBlocked("lease no longer supports this claim")
            lease = Lease(f"egg:{egg_id}", row[0], row[1], row[2])
        self.hive.ledger.check_fence_now(*lease.fence)
        return Claim(egg, lease, cap, profile)

    # -- delivering ----------------------------------------------------------------

    def deliver(self, claim: Claim, output: dict[str, Any]) -> str:
        validator = jsonschema.Draft202012Validator(claim.egg.schema)
        errors = sorted(validator.iter_errors(output), key=lambda e: list(e.path))
        if errors:
            raise OutputRejected(f"{claim.egg.egg_id}: {errors[0].message}")
        self.hive.ledger.check_fence_now(*claim.lease.fence)  # don't stage anything for a lapsed claim
        body = canonicalize({"egg_id": claim.egg.egg_id, "output": output})
        sha = self.hive.enclaves.stage(f"{claim.egg.egg_id}.json", body)
        return self._record_delivery(claim, sha)

    def _record_delivery(self, claim: Claim, sha: str) -> str:
        """Record an already read-back staging effect, fenced by the existing claim."""
        self.hive.ledger.append(
            "egg.delivered",
            self.actor,
            {
                "artifact_sha": sha,
                "egg_id": claim.egg.egg_id,
                "lease_token": claim.lease.token,
                "token_id": claim.capability.token_id,
            },
            fence=claim.lease.fence,
            op_id=f"egg.delivered:{claim.egg.egg_id}",
        )
        self.hive.leases.release(claim.lease)
        return sha
