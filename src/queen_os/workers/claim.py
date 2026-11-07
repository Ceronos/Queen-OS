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

from queen_os.authority.tokens import Capability, Grant
from queen_os.comb.leases import Lease, LeaseHeld
from queen_os.comb.projection import EggView, fold_eggs, ready
from queen_os.hive import Hive
from queen_os.queen.egg import TaskEgg, load
from queen_os.queen.valve import Profile, ValveRefusal, profile_for
from queen_os.serial.jcs import canonicalize

_WORKER_RE = re.compile(r"^[a-z0-9][a-z0-9_.-]{0,62}$")


class OutputRejected(ValueError):
    """The worker's output violates the egg's schema. Nothing was staged."""


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
    ) -> None:
        if not _WORKER_RE.match(worker_id):
            raise ValueError(f"worker id {worker_id!r} must match {_WORKER_RE.pattern}")
        if not 0.0 < threshold <= 1.0:
            raise ValueError("threshold must be in (0, 1]")
        self.hive = hive
        self.actor = f"worker:{worker_id}"
        self.threshold = threshold
        self.providers = providers
        self.models = models

    # -- choosing ------------------------------------------------------------------

    def candidates(self) -> list[EggView]:
        eggs = [e for e in ready(fold_eggs(self.hive.ledger)) if response(e.stimulus, self.threshold) >= 0.5]
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
        cap = self.hive.authority().issue(self.actor, f"egg:{egg.egg_id}", grant, ttl_ms=max(ttl, 1))
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

    # -- delivering ----------------------------------------------------------------

    def deliver(self, claim: Claim, output: dict[str, Any]) -> str:
        validator = jsonschema.Draft202012Validator(claim.egg.schema)
        errors = sorted(validator.iter_errors(output), key=lambda e: list(e.path))
        if errors:
            raise OutputRejected(f"{claim.egg.egg_id}: {errors[0].message}")
        self.hive.ledger.check_fence_now(*claim.lease.fence)  # don't stage anything for a lapsed claim
        body = canonicalize({"egg_id": claim.egg.egg_id, "output": output})
        sha = self.hive.enclaves.stage(f"{claim.egg.egg_id}.json", body)
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
