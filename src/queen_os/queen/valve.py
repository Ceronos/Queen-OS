"""Bresslau's Valve: systemic risk G → execution profile (Thesis §5.3).

    G ≥ 0.5  → DIPLOID worker: deterministic (T ≤ 0.2), strict output schema, cross-lineage
               quorum when G is high
    G <  0.5 → HAPLOID drone: exploratory (T ≥ 0.9), schema optional, no quorum

G is computed from the egg, never from model text, using rules that fail closed:

* each requested tool has a risk weight, and an **unknown tool weighs 0.9**, so a new tool is
  treated as dangerous until someone classifies it
* a declared ``diploid`` egg has a floor of G = 0.5 (the Queen can always demand rigor)
* G = max(floor, max tool risk): risk never averages down
* a ``haploid`` egg whose G comes out ≥ 0.5 is **escalated** to diploid, and if its schema
  is not strict enough for diploid execution, the valve refuses it (an egg can't
  downgrade its own risk by declaring itself haploid)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from queen_os.queen.egg import EggError, TaskEgg

Ploidy = Literal["diploid", "haploid"]

DIPLOID_THRESHOLD = 0.5
QUORUM_THRESHOLD = 0.8
UNKNOWN_TOOL_RISK = 0.9

# Prefix → risk. The longest matching prefix wins. Reads are cheap. Anything that
# mutates state, leaves the host or executes code is not.
TOOL_RISK: dict[str, float] = {
    "read_": 0.1,
    "list_": 0.1,
    "search_": 0.2,
    "web_fetch": 0.4,
    "web_search": 0.3,
    "write_": 0.6,
    "edit_": 0.6,
    "delete_": 0.9,
    "http_": 0.7,
    "send_": 0.8,
    "shell": 0.95,
    "exec_": 0.95,
    "python": 0.9,
}


class ValveRefusal(EggError):
    pass


@dataclass(frozen=True)
class Profile:
    risk: float
    ploidy: Ploidy
    escalated: bool
    temperature: float
    strict_schema: bool
    quorum: int  # number of *distinct-lineage* verifiers required by the gate (M2)
    max_output_tokens: int
    max_calls: int


def tool_risk(tool: str) -> float:
    matches = [p for p in TOOL_RISK if tool == p or tool.startswith(p)]
    return TOOL_RISK[max(matches, key=len)] if matches else UNKNOWN_TOOL_RISK


def strict_enough(schema: dict[str, object]) -> bool:
    return schema.get("type") == "object" and bool(schema.get("properties")) and bool(schema.get("required"))


def risk_of(egg: TaskEgg) -> float:
    floor = DIPLOID_THRESHOLD if egg.ploidy == "diploid" else 0.0
    return max([floor, *(tool_risk(t) for t in egg.tools)])


def profile_for(egg: TaskEgg) -> Profile:
    g = risk_of(egg)
    if g < DIPLOID_THRESHOLD:
        return Profile(g, "haploid", False, 0.9, False, 0, 1024, 3)
    escalated = egg.ploidy == "haploid"
    if not strict_enough(egg.schema):
        raise ValveRefusal(
            f"{egg.egg_id}: risk G={g:.2f} requires diploid execution, but its schema is not strict "
            "(needs type=object with properties and required)"
        )
    quorum = 2 if g >= QUORUM_THRESHOLD else 0
    return Profile(g, "diploid", escalated, 0.0 if g >= QUORUM_THRESHOLD else 0.2, True, quorum, 512, 1)
