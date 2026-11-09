"""State is a pure fold of the ledger (Thesis §4.3). Nothing here writes. Delete it and rebuild at will.

Egg lifecycle, driven only by ledger events:

    laid ─▶ claimed ─▶ delivered ─▶ hatched      (gate promoted the artifact)
                │           └─────▶ purged       (gate quarantined it: oophagy)
                └─ claim lapses (lease expired, nothing delivered) ─▶ claimable again

An egg is **ready** when it is laid, all parents are hatched, and it is neither hatched
nor purged. Ready eggs with no live lease are what workers may claim.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Literal

from queen_os.comb.ledger import Event, Ledger

State = Literal["laid", "claimed", "delivered", "hatched", "purged"]
TERMINAL: frozenset[str] = frozenset({"hatched", "purged"})


@dataclass
class EggView:
    egg_id: str
    goal_id: str
    stimulus: float
    parents: tuple[str, ...]
    state: State = "laid"
    claims: list[dict[str, object]] = field(default_factory=list)
    artifact_sha: str | None = None
    laid_seq: int = 0


def fold_eggs(ledger: Ledger) -> dict[str, EggView]:
    return fold_events(ledger.events())


def fold_events(events: Iterable[Event]) -> dict[str, EggView]:
    """Fold an explicitly verified event prefix; no mutable tables or effects."""
    eggs: dict[str, EggView] = {}
    for ev in events:
        p = ev.payload
        if ev.kind == "egg.laid":
            eggs[p["egg_id"]] = EggView(
                p["egg_id"], p["goal_id"], float(p["stimulus"]), tuple(p["parents"]), laid_seq=ev.seq
            )
            continue
        egg = eggs.get(p.get("egg_id", "")) if isinstance(p, dict) else None
        if egg is None or egg.state in TERMINAL:
            continue
        if ev.kind == "egg.claimed":
            egg.state = "claimed"
            egg.claims.append({"worker": ev.actor, "token": p["lease_token"], "seq": ev.seq})
        elif ev.kind == "egg.delivered":
            egg.state, egg.artifact_sha = "delivered", p["artifact_sha"]
        elif ev.kind == "egg.hatched":
            egg.state = "hatched"
        elif ev.kind == "egg.purged":
            egg.state = "purged"
    return eggs


def ready(eggs: dict[str, EggView]) -> list[EggView]:
    """Eggs whose parents are all hatched and that are not finished or awaiting the gate."""
    return [
        e
        for e in eggs.values()
        if e.state in ("laid", "claimed") and all(eggs.get(p) and eggs[p].state == "hatched" for p in e.parents)
    ]
