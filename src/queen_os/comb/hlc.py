"""Hybrid Logical Clock (L, C, node_id).

L is wall-clock milliseconds (PTP-disciplined when the host has it, plain system time
otherwise). C breaks ties and absorbs clock regressions, so stamps are strictly
increasing even if the wall clock steps backwards. The encoded form sorts
lexicographically in causal order.
"""

from __future__ import annotations

import re
import time
from collections.abc import Callable
from dataclasses import dataclass

_NODE_RE = re.compile(r"^[A-Za-z0-9_.]{1,64}$")


@dataclass(frozen=True, order=True)
class HLCStamp:
    wall_ms: int
    counter: int
    node_id: str

    def encode(self) -> str:
        return f"{self.wall_ms:015d}-{self.counter:08d}-{self.node_id}"

    @classmethod
    def decode(cls, text: str) -> HLCStamp:
        wall, counter, node = text.split("-", 2)
        return cls(int(wall), int(counter), node)


def validate_node_id(node_id: str) -> str:
    if not _NODE_RE.match(node_id):
        raise ValueError(f"node_id {node_id!r} must match {_NODE_RE.pattern}")
    return node_id


class HybridLogicalClock:
    def __init__(self, node_id: str, wall_ms: Callable[[], int] | None = None) -> None:
        self.node_id = validate_node_id(node_id)
        self._wall = wall_ms or (lambda: time.time_ns() // 1_000_000)

    def tick(self, last: HLCStamp | None) -> HLCStamp:
        """Next local stamp, strictly after ``last`` (the ledger's persisted head)."""
        now = self._wall()
        if last is None or now > last.wall_ms:
            return HLCStamp(now, 0, self.node_id)
        return HLCStamp(last.wall_ms, last.counter + 1, self.node_id)

    def receive(self, last: HLCStamp | None, remote: HLCStamp) -> HLCStamp:
        """Merge a remote stamp (federation). Result is after both ``last`` and ``remote``."""
        now = self._wall()
        local_l = last.wall_ms if last else -1
        wall = max(now, local_l, remote.wall_ms)
        if wall == local_l == remote.wall_ms:
            counter = max(last.counter if last else 0, remote.counter) + 1
        elif wall == local_l:
            counter = (last.counter if last else 0) + 1
        elif wall == remote.wall_ms:
            counter = remote.counter + 1
        else:
            counter = 0
        return HLCStamp(wall, counter, self.node_id)
