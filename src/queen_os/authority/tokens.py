"""Capability tokens: the only source of authority (AF-REMEDY-V1 §1.5, CLAUDE.md law 3).

A token is a host-signed grant: *subject* may perform *these actions* within *this
scope* until *this time*, at most *this many times*. Model output is never consulted.
A prompt that says "you are authorized" changes nothing, because authorization is
checked against signed bytes that only host code mints.

Lifecycle, all on the ledger:
    capability.issued   the token body + signature (op_id = token id)
    capability.revoked  by token id
    capability.spent    one call reserved *before* it runs, atomically with the budget check,
                        so concurrent holders of one token cannot overspend it
    inference.receipt   carries ``token_id`` and the spend's seq
"""

from __future__ import annotations

import fnmatch
import uuid
from dataclasses import dataclass
from typing import Any

from queen_os.comb.ledger import Ledger
from queen_os.crypto.keys import Signer, public_from_hex, verify
from queen_os.serial.jcs import canonicalize

ISSUED = "capability.issued"
REVOKED = "capability.revoked"
SPENT = "capability.spent"


class AuthorityError(PermissionError):
    """A request is not covered by a valid capability. Fail closed."""


@dataclass(frozen=True)
class Grant:
    """What a token allows. Patterns use fnmatch globs (``anthropic``, ``claude-*``)."""

    tools: tuple[str, ...] = ()
    providers: tuple[str, ...] = ()
    models: tuple[str, ...] = ()
    max_output_tokens: int = 1024
    max_calls: int = 1

    def to_json(self) -> dict[str, Any]:
        return {
            "max_calls": self.max_calls,
            "max_output_tokens": self.max_output_tokens,
            "models": list(self.models),
            "providers": list(self.providers),
            "tools": list(self.tools),
        }

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> Grant:
        return cls(
            tuple(data["tools"]),
            tuple(data["providers"]),
            tuple(data["models"]),
            int(data["max_output_tokens"]),
            int(data["max_calls"]),
        )


@dataclass(frozen=True)
class Capability:
    token_id: str
    issuer: str
    subject: str
    scope: str
    grant: Grant
    not_before_ms: int
    expires_ms: int
    signature: str

    def body(self) -> dict[str, Any]:
        return {
            "expires_ms": self.expires_ms,
            "grant": self.grant.to_json(),
            "issuer": self.issuer,
            "not_before_ms": self.not_before_ms,
            "scope": self.scope,
            "subject": self.subject,
            "token_id": self.token_id,
            "v": 1,
        }

    def to_json(self) -> dict[str, Any]:
        return {**self.body(), "signature": self.signature}

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> Capability:
        return cls(
            data["token_id"],
            data["issuer"],
            data["subject"],
            data["scope"],
            Grant.from_json(data["grant"]),
            int(data["not_before_ms"]),
            int(data["expires_ms"]),
            data["signature"],
        )


class Authority:
    def __init__(self, ledger: Ledger, signer: Signer) -> None:
        self.ledger = ledger
        self.signer = signer

    def issue(
        self, subject: str, scope: str, grant: Grant, ttl_ms: int, *, not_after_ms: int | None = None
    ) -> Capability:
        """Issue with a relative lifetime and optional absolute upper deadline.

        The host may narrow expiry to a source lease's fixed deadline. Compute both
        from this one clock read; never add an earlier caller's remaining TTL to a
        later clock and accidentally extend authority beyond that lease.
        """
        if ttl_ms <= 0 or grant.max_calls <= 0 or grant.max_output_tokens <= 0:
            raise ValueError("ttl, max_calls and max_output_tokens must be positive")
        if not_after_ms is not None and type(not_after_ms) is not int:
            raise ValueError("absolute expiry deadline must be an integer")
        now = self.ledger.now()
        expires = now + ttl_ms if not_after_ms is None else min(now + ttl_ms, not_after_ms)
        if expires <= now:
            raise AuthorityError("capability deadline has expired; no capability issued")
        unsigned = Capability(f"cap_{uuid.uuid4().hex}", self.signer.key_id, subject, scope, grant, now, expires, "")
        signature = self.signer.sign(canonicalize(unsigned.body()))
        cap = Capability(**{**unsigned.__dict__, "signature": signature})
        self.ledger.append(ISSUED, f"authority:{self.signer.key_id}", cap.to_json(), op_id=f"{ISSUED}:{cap.token_id}")
        return cap

    def revoke(self, token_id: str, reason: str) -> None:
        self.ledger.append(
            REVOKED,
            f"authority:{self.signer.key_id}",
            {"token_id": token_id, "reason": reason},
            op_id=f"{REVOKED}:{token_id}",
        )

    # -- checking ------------------------------------------------------------------

    def _verify_signature(self, cap: Capability) -> None:
        public_hex = self.ledger.public_keys().get(cap.issuer)
        if public_hex is None:
            raise AuthorityError(f"{cap.token_id}: unknown issuer {cap.issuer}")
        if not verify(public_from_hex(public_hex), canonicalize(cap.body()), cap.signature):
            raise AuthorityError(f"{cap.token_id}: bad signature")

    def _assert_issued_and_live(self, cap: Capability) -> None:
        issued = self.ledger.find_op(f"{ISSUED}:{cap.token_id}")
        if issued is None or issued.payload != cap.to_json():
            raise AuthorityError(f"{cap.token_id}: not issued by this hive's ledger")
        if self.ledger.find_op(f"{REVOKED}:{cap.token_id}") is not None:
            raise AuthorityError(f"{cap.token_id}: revoked")
        now = self.ledger.now()
        if not cap.not_before_ms <= now < cap.expires_ms:
            raise AuthorityError(f"{cap.token_id}: outside its validity window")

    def uses(self, token_id: str) -> int:
        return sum(1 for _ in self._spends(token_id))

    def _spends(self, token_id: str) -> list[int]:
        with self.ledger.transaction() as db:
            rows = db.execute(
                "SELECT seq FROM events WHERE kind=? AND json_extract(payload, '$.token_id')=?", (SPENT, token_id)
            ).fetchall()
        return [int(r[0]) for r in rows]

    def _reserve(self, cap: Capability, actor: str, action: dict[str, Any], completion_tokens: int = 0) -> int:
        """Atomically: re-check revocation/expiry, check the budget, record the spend. Returns its seq."""
        with self.ledger.transaction() as db:
            if db.execute("SELECT 1 FROM events WHERE op_id=?", (f"{REVOKED}:{cap.token_id}",)).fetchone():
                raise AuthorityError(f"{cap.token_id}: revoked")
            if self.ledger.now() >= cap.expires_ms:
                raise AuthorityError(f"{cap.token_id}: expired")
            used = db.execute(
                "SELECT COUNT(*) FROM events WHERE kind=? AND json_extract(payload, '$.token_id')=?",
                (SPENT, cap.token_id),
            ).fetchone()[0]
            if used >= cap.grant.max_calls:
                raise AuthorityError(f"{cap.token_id}: call budget ({cap.grant.max_calls}) exhausted")
            from queen_os.queen.budget import PlanBudgetError, plan_charge

            try:
                charge = plan_charge(self.ledger, cap.scope, action, completion_tokens)
            except (PlanBudgetError, KeyError, TypeError) as exc:
                raise AuthorityError("published plan budget refused") from exc
            payload = {"action": action, "n": int(used) + 1, "token_id": cap.token_id}
            if charge is not None:
                payload["plan"] = charge
            return self.ledger.append_locked(db, SPENT, actor, payload)

    def authorize_inference(self, cap: Capability, actor: str, provider: str, model: str, max_tokens: int) -> int:
        """Check every rule, then reserve one call. Returns the ``capability.spent`` seq."""
        self._verify_signature(cap)
        self._assert_issued_and_live(cap)
        if not fnmatch.fnmatchcase(actor, cap.subject):
            raise AuthorityError(f"{cap.token_id}: actor {actor!r} is not subject {cap.subject!r}")
        g = cap.grant
        if not any(fnmatch.fnmatchcase(provider, p) for p in g.providers):
            raise AuthorityError(f"{cap.token_id}: provider {provider!r} not granted")
        if not any(fnmatch.fnmatchcase(model, m) for m in g.models):
            raise AuthorityError(f"{cap.token_id}: model {model!r} not granted")
        if max_tokens > g.max_output_tokens:
            raise AuthorityError(f"{cap.token_id}: {max_tokens} output tokens > granted {g.max_output_tokens}")
        return self._reserve(cap, actor, {"type": "inference", "provider": provider, "model": model}, max_tokens)

    def authorize_tool(self, cap: Capability, actor: str, tool: str) -> int:
        self._verify_signature(cap)
        self._assert_issued_and_live(cap)
        if not fnmatch.fnmatchcase(actor, cap.subject):
            raise AuthorityError(f"{cap.token_id}: actor {actor!r} is not subject {cap.subject!r}")
        if tool not in cap.grant.tools:  # tools are exact names; no globs
            raise AuthorityError(f"{cap.token_id}: tool {tool!r} not granted")
        return self._reserve(cap, actor, {"type": "tool", "tool": tool})
