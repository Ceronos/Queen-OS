"""TaskEgg: the 7-tuple unit of work (Thesis §5.1).

    TaskEgg_j = ⟨ID, Ploidy, Input, Schema, Tools, Stimulus, Signature⟩

V5 additions, all covered by the signature:
* ``goal_id`` and ``parents`` make eggs a DAG. A parent must already be laid, so the graph
  is acyclic by construction: no cycle can be expressed.
* ``issuer`` is the Dufour key id that signed the egg.

Bounds and rules (fail closed):
* Input ≤ ``MAX_INPUT_BYTES`` of canonical JSON. The spec says "< 2,000 tokens". Bytes/4 is a
  tokenizer-independent approximation, recorded as such, so the bound means the same for every model.
* Schema must be a valid JSON Schema (Draft 2020-12). Diploid eggs need a non-trivial
  object schema, because a diploid output must be checkable against a strict contract.
* Stimulus ∈ [0, 1] (Page-Robinson response threshold input).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any, Literal

import jsonschema

from queen_os.comb.ledger import Event
from queen_os.crypto.keys import public_from_hex, verify
from queen_os.hive import Hive
from queen_os.serial.jcs import canonicalize

Ploidy = Literal["diploid", "haploid"]
LAID = "egg.laid"
MAX_INPUT_BYTES = 8_000  # ≈ 2,000 tokens at ~4 bytes/token


class EggError(ValueError):
    pass


@dataclass(frozen=True)
class TaskEgg:
    egg_id: str
    goal_id: str
    ploidy: Ploidy
    input: dict[str, Any]
    schema: dict[str, Any]
    tools: tuple[str, ...]
    stimulus: float
    parents: tuple[str, ...] = ()
    issuer: str = ""
    signature: str = field(default="", repr=False)

    def body(self) -> dict[str, Any]:
        return {
            "egg_id": self.egg_id,
            "goal_id": self.goal_id,
            "input": self.input,
            "issuer": self.issuer,
            "parents": list(self.parents),
            "ploidy": self.ploidy,
            "schema": self.schema,
            "stimulus": self.stimulus,
            "tools": list(self.tools),
            "v": 1,
        }

    def to_json(self) -> dict[str, Any]:
        return {**self.body(), "signature": self.signature}

    @classmethod
    def from_json(cls, d: dict[str, Any]) -> TaskEgg:
        return cls(
            d["egg_id"],
            d["goal_id"],
            d["ploidy"],
            d["input"],
            d["schema"],
            tuple(d["tools"]),
            float(d["stimulus"]),
            tuple(d["parents"]),
            d["issuer"],
            d["signature"],
        )


def validate_shape(egg: TaskEgg) -> None:
    if egg.ploidy not in ("diploid", "haploid"):
        raise EggError(f"ploidy must be diploid|haploid, got {egg.ploidy!r}")
    if not isinstance(egg.input, dict):
        raise EggError("input must be a JSON object")
    size = len(canonicalize(egg.input))
    if size > MAX_INPUT_BYTES:
        raise EggError(f"input is {size} canonical bytes > {MAX_INPUT_BYTES} (≈2,000-token bound)")
    if not 0.0 <= egg.stimulus <= 1.0:
        raise EggError("stimulus must be in [0, 1]")
    try:
        jsonschema.Draft202012Validator.check_schema(egg.schema)
    except jsonschema.SchemaError as exc:
        raise EggError(f"schema is not valid JSON Schema 2020-12: {exc.message}") from None
    if egg.ploidy == "diploid" and not (egg.schema.get("type") == "object" and egg.schema.get("properties")):
        raise EggError("diploid eggs need a strict object schema with declared properties")
    if len(set(egg.tools)) != len(egg.tools) or any(not t.isidentifier() for t in egg.tools):
        raise EggError("tools must be unique identifiers")
    if egg.egg_id in egg.parents:
        raise EggError("an egg cannot be its own parent")


def lay(
    hive: Hive,
    goal_id: str,
    ploidy: Ploidy,
    input: dict[str, Any],  # noqa: A002 - the spec's field name
    schema: dict[str, Any],
    tools: tuple[str, ...] = (),
    stimulus: float = 0.5,
    parents: tuple[str, ...] = (),
    actor: str = "queen",
) -> TaskEgg:
    """Validate, sign with the hive's Dufour key, and append ``egg.laid``. Parents must already exist."""
    signer = hive.ledger.signer
    if signer is None:
        raise EggError("hive has no signer")
    egg = TaskEgg(
        f"egg_{uuid.uuid4().hex}",
        goal_id,
        ploidy,
        input,
        schema,
        tuple(tools),
        float(stimulus),
        tuple(parents),
        signer.key_id,
    )
    validate_shape(egg)
    for parent in egg.parents:
        if hive.ledger.find_op(f"{LAID}:{parent}") is None:
            raise EggError(f"parent {parent} has not been laid (DAG is acyclic by construction)")
    signed = TaskEgg(**{**egg.__dict__, "signature": signer.sign(canonicalize(egg.body()))})
    hive.ledger.append(LAID, actor, signed.to_json(), op_id=f"{LAID}:{signed.egg_id}")
    return signed


def verify_egg(hive: Hive, egg: TaskEgg) -> None:
    validate_shape(egg)
    public_hex = hive.ledger.public_keys().get(egg.issuer)
    if public_hex is None:
        raise EggError(f"{egg.egg_id}: unknown issuer {egg.issuer}")
    if not verify(public_from_hex(public_hex), canonicalize(egg.body()), egg.signature):
        raise EggError(f"{egg.egg_id}: bad Dufour signature")


def load(hive: Hive, egg_id: str) -> TaskEgg:
    event: Event | None = hive.ledger.find_op(f"{LAID}:{egg_id}")
    if event is None:
        raise EggError(f"egg {egg_id} not found")
    egg = TaskEgg.from_json(event.payload)
    verify_egg(hive, egg)
    return egg
