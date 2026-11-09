"""VerificationGate (Pillar 2 §3): the only path from staging/ to committed/.

The gate trusts nothing the worker said. For a delivered egg it re-derives every check,
deterministic ones first (REMEDY §1.4: no LLM vote before schema/digest/receipt checks):

  artifact_present      the staged file exists
  artifact_digest       its SHA-256 equals the digest in ``egg.delivered``
  artifact_envelope     canonical JSON ``{"egg_id", "output"}`` for *this* egg
  egg_signature         the egg still verifies under the hive's Dufour key
  output_schema         the output validates against the egg's schema (re-checked, not trusted)
  witnessed_inference   ≥ 1 inference receipt under the delivering capability, each re-derived
                        from raw bytes; fixtures are refused in production (Non-Simulation Contract)
  output_matches_receipt  the delivered output equals the JSON the model actually returned in a
                        verified receipt, so a worker can't invent output and attach an unrelated
                        real receipt (M1 strictness; post-processing workers will need a declared
                        transform)
  quorum                eggs whose valve profile demands cross-lineage quorum are HELD, not
                        promoted, until the M2 quorum verifier exists (fail closed, never skipped)

Outcomes are ledger events, fenced by a ``gate:<egg>`` lease so two gates can't both decide:

  PASS → ``Enclaves.promote`` (atomic no-replace, QOS-0009) → ``egg.hatched``
  FAIL → oophagy: staged artifact moved to quarantine/, worker capability revoked, ``egg.purged``
  HOLD → ``egg.held`` (no state change; re-reviewable once the blocking condition is met)

Every decision stores its full evidence pack in the content-addressed blob store and references
it by digest, so a verdict can be audited from the hive alone.
"""

from __future__ import annotations

import contextlib
import json
from dataclasses import dataclass, field
from typing import Any, Literal

import jsonschema

from queen_os.authority.tokens import REVOKED
from queen_os.comb.enclaves import EnclaveViolation
from queen_os.comb.leases import LeaseHeld
from queen_os.comb.ledger import StaleFence
from queen_os.comb.projection import fold_eggs
from queen_os.hive import Hive
from queen_os.providers.receipt import RECEIPT_KIND, NonSimulationViolation, verify_receipt
from queen_os.queen.egg import EggError, load
from queen_os.serial.afser import DigestDivergence, sha256_hex
from queen_os.serial.jcs import canonicalize

Verdict = Literal["hatched", "purged", "held"]


class GateError(RuntimeError):
    pass


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise ValueError("duplicate JSON key")
        value[key] = item
    return value


def _reject_constant(value: str) -> Any:
    raise ValueError(f"nonfinite JSON constant: {value}")


@dataclass
class Evidence:
    egg_id: str
    checks: list[dict[str, Any]] = field(default_factory=list)

    def record(self, name: str, ok: bool, detail: str = "") -> bool:
        self.checks.append({"check": name, "detail": detail, "ok": ok})
        return ok

    @property
    def failed(self) -> list[str]:
        return [c["check"] for c in self.checks if not c["ok"]]


@dataclass(frozen=True)
class Decision:
    verdict: Verdict
    egg_id: str
    evidence_sha: str
    failed: tuple[str, ...]


class Gate:
    def __init__(self, hive: Hive, name: str = "vigil") -> None:
        self.hive = hive
        self.actor = f"gate:{name}"

    def review(self, egg_id: str, lease_ttl_ms: int = 30_000) -> Decision:
        try:
            lease = self.hive.leases.acquire(f"gate:{egg_id}", self.actor, lease_ttl_ms)
        except LeaseHeld as exc:
            raise GateError(f"{egg_id} is under review by another gate") from exc
        try:
            return self._review(egg_id, lease.fence)
        finally:
            with contextlib.suppress(StaleFence):  # a lapsed review lease is harmless: decisions were fenced
                self.hive.leases.release(lease)

    # -- the review ----------------------------------------------------------------

    def _review(self, egg_id: str, fence: tuple[str, int]) -> Decision:
        view = fold_eggs(self.hive.ledger).get(egg_id)
        if view is None:
            raise GateError(f"unknown egg {egg_id}")
        if view.state in ("hatched", "purged"):
            prior = self.hive.ledger.find_op(f"egg.{view.state}:{egg_id}")
            assert prior is not None
            return Decision(view.state, egg_id, prior.payload["evidence_sha"], tuple(prior.payload.get("failed", ())))
        if view.state != "delivered":
            raise GateError(f"{egg_id} is {view.state}, not delivered")
        # A prior promotion may have completed before its verdict append returned.
        # Catalog recovery never overwrites or retrospectively purges that effect.
        laid = self.hive.ledger.find_op("egg.laid:" + egg_id)
        if (
            laid is not None
            and self.hive.ledger.find_op("goal.run_prepared:" + laid.payload["goal_id"]) is not None
            and (self.hive.enclaves.committed / (egg_id + ".json")).exists()
        ):
            raise GateError("unrecorded catalog promotion requires manual reconciliation")

        delivered = self.hive.ledger.find_op(f"egg.delivered:{egg_id}")
        assert delivered is not None
        ev = Evidence(egg_id)
        output = self._check_artifact(ev, egg_id, delivered.payload["artifact_sha"])
        egg = self._check_egg(ev, egg_id)
        if egg is not None and output is not None:
            ev.record(
                "output_schema",
                not list(jsonschema.Draft202012Validator(egg.schema).iter_errors(output)),
                "re-validated by the gate",
            )
        self._check_witness(ev, delivered.payload["token_id"], output, egg.schema if egg is not None else None)
        if egg is not None and self.hive.ledger.find_op("goal.run_prepared:" + egg.goal_id) is not None:
            from queen_os.workers.execution import ORACLE, check_delivery, contract_hash

            try:
                if output is None:
                    raise ValueError("missing output")
                check_delivery(self.hive, egg, output, delivered)
                ev.record("catalog_provenance_and_oracle", True, f"{ORACLE}:{contract_hash()}")
            except (ValueError, PermissionError, KeyError, TypeError, OSError) as exc:
                ev.record("catalog_provenance_and_oracle", False, f"{ORACLE}:{contract_hash()}: {type(exc).__name__}")

        claimed = [e for e in self.hive.ledger.events(kind="egg.claimed") if e.payload["egg_id"] == egg_id]
        quorum = int(claimed[-1].payload["profile"]["quorum"]) if claimed else 0

        if ev.failed:
            return self._purge(egg_id, ev, delivered.payload, fence)
        if quorum >= 2:
            ev.record("quorum", False, f"profile requires {quorum} cross-lineage verifiers; M2 verifier not built")
            return self._hold(egg_id, ev, fence)
        return self._hatch(egg_id, ev, delivered.payload["artifact_sha"], fence)

    def _check_artifact(self, ev: Evidence, egg_id: str, expected_sha: str) -> dict[str, Any] | None:
        path = self.hive.enclaves.staging / f"{egg_id}.json"
        if not ev.record("artifact_present", path.exists(), str(path.name)):
            return None
        data = path.read_bytes()
        if not ev.record("artifact_digest", sha256_hex(data) == expected_sha, expected_sha):
            return None
        try:
            env = json.loads(data)
            ok = (
                isinstance(env, dict)
                and set(env) == {"egg_id", "output"}
                and env["egg_id"] == egg_id
                and isinstance(env["output"], dict)
                and canonicalize(env) == data
            )
        except (ValueError, TypeError):
            ok = False
        if not ev.record("artifact_envelope", ok, "canonical {egg_id, output}"):
            return None
        return dict(env["output"])

    def _check_egg(self, ev: Evidence, egg_id: str) -> Any:
        try:
            egg = load(self.hive, egg_id)
        except EggError as exc:
            ev.record("egg_signature", False, str(exc))
            return None
        ev.record("egg_signature", True)
        return egg

    def _check_witness(
        self, ev: Evidence, token_id: str, output: dict[str, Any] | None, schema: dict[str, Any] | None
    ) -> None:
        receipts = [e for e in self.hive.ledger.events(kind=RECEIPT_KIND) if e.payload.get("token_id") == token_id]
        if not ev.record("witnessed_inference", bool(receipts), f"{len(receipts)} receipt(s) under {token_id}"):
            return
        texts: list[str] = []
        for r in receipts:
            try:
                texts.append(verify_receipt(self.hive, r).text)
            except (NonSimulationViolation, DigestDivergence, OSError) as exc:
                ev.record("witnessed_inference", False, f"receipt seq {r.seq}: {exc}")
                return
        ev.record("witnessed_inference", True, f"receipt seqs {[r.seq for r in receipts]} re-derived")
        if output is None or schema is None:
            return
        matched = False
        validator = jsonschema.Draft202012Validator(schema)
        for text in texts:
            try:
                value = json.loads(text, object_pairs_hook=_unique_object, parse_constant=_reject_constant)
                if list(validator.iter_errors(value)):
                    continue
                # Python equality conflates True/1 (also nested); JCS preserves JSON types.
                # Canonicalization also rejects nonfinite numbers produced by exponent overflow.
                matched = canonicalize(value) == canonicalize(output)
                if matched:
                    break
            except (ValueError, TypeError, RecursionError):
                continue
        ev.record("output_matches_receipt", matched, "schema-valid, unambiguous model JSON matches canonical delivery")

    # -- outcomes ------------------------------------------------------------------

    def _store(self, ev: Evidence, verdict: Verdict) -> str:
        return self.hive.blobs.put(canonicalize({"checks": ev.checks, "egg_id": ev.egg_id, "verdict": verdict}))

    def _hatch(self, egg_id: str, ev: Evidence, artifact_sha: str, fence: tuple[str, int]) -> Decision:
        try:
            self.hive.enclaves.promote(f"{egg_id}.json", artifact_sha)
        except (EnclaveViolation, DigestDivergence) as exc:
            ev.record("promotion", False, str(exc))
            return self._purge(egg_id, ev, {"artifact_sha": artifact_sha}, fence)
        ev.record("promotion", True, f"committed/{egg_id}.json")
        evidence_sha = self._store(ev, "hatched")
        self.hive.ledger.append(
            "egg.hatched",
            self.actor,
            {"artifact_sha": artifact_sha, "egg_id": egg_id, "evidence_sha": evidence_sha},
            fence=fence,
            op_id=f"egg.hatched:{egg_id}",
        )
        return Decision("hatched", egg_id, evidence_sha, ())

    def _purge(self, egg_id: str, ev: Evidence, delivered: dict[str, Any], fence: tuple[str, int]) -> Decision:
        staged = self.hive.enclaves.staging / f"{egg_id}.json"
        if staged.exists():
            self.hive.enclaves.quarantine(f"{egg_id}.json")
        token_id = delivered.get("token_id")
        if token_id and self.hive.ledger.find_op(f"{REVOKED}:{token_id}") is None:
            self.hive.authority().revoke(token_id, f"oophagy: {', '.join(ev.failed)}")
        evidence_sha = self._store(ev, "purged")
        failed = tuple(ev.failed)
        self.hive.ledger.append(
            "egg.purged",
            self.actor,
            {"egg_id": egg_id, "evidence_sha": evidence_sha, "failed": list(failed), "reason": "oophagy"},
            fence=fence,
            op_id=f"egg.purged:{egg_id}",
        )
        return Decision("purged", egg_id, evidence_sha, failed)

    def _hold(self, egg_id: str, ev: Evidence, fence: tuple[str, int]) -> Decision:
        evidence_sha = self._store(ev, "held")
        self.hive.ledger.append(
            "egg.held",
            self.actor,
            {"egg_id": egg_id, "evidence_sha": evidence_sha, "failed": ev.failed},
            fence=fence,
        )
        return Decision("held", egg_id, evidence_sha, tuple(ev.failed))
