from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from queen_os.hive import Hive
from queen_os.queen.egg import MAX_INPUT_BYTES, EggError, TaskEgg, lay, load, verify_egg

STRICT = {
    "type": "object",
    "properties": {"answer": {"type": "string"}},
    "required": ["answer"],
    "additionalProperties": False,
}


@pytest.fixture
def hive(tmp_path: Path):  # type: ignore[no-untyped-def]
    with Hive.init(tmp_path / "h", "q") as h:
        yield h


def test_lay_load_roundtrip_and_dag(hive: Hive) -> None:
    root = lay(hive, "goal-1", "diploid", {"task": "summarize"}, STRICT, tools=("read_file",), stimulus=0.8)
    child = lay(hive, "goal-1", "haploid", {"task": "brainstorm"}, {}, parents=(root.egg_id,))
    assert load(hive, child.egg_id) == child and load(hive, root.egg_id).tools == ("read_file",)
    assert hive.ledger.verify_chain(require_signatures=True) == 3


@pytest.mark.parametrize(
    ("kwargs", "msg"),
    [
        ({"ploidy": "triploid"}, "ploidy"),
        ({"input": {"x": "a" * MAX_INPUT_BYTES}}, "2,000-token"),
        ({"stimulus": 1.5}, "stimulus"),
        ({"schema": {"type": "not-a-type"}}, "JSON Schema"),
        ({"schema": {}}, "diploid eggs need a strict"),
        ({"tools": ("read_file", "read_file")}, "unique"),
        ({"tools": ("rm -rf",)}, "identifiers"),
        ({"parents": ("egg_does_not_exist",)}, "not been laid"),
    ],
)
def test_malformed_eggs_fail_closed(hive: Hive, kwargs: dict, msg: str) -> None:  # type: ignore[type-arg]
    args = {"goal_id": "g", "ploidy": "diploid", "input": {"t": 1}, "schema": STRICT, **kwargs}
    with pytest.raises(EggError, match=msg):
        lay(hive, **args)
    assert [e.kind for e in hive.ledger.events()] == ["hive.genesis"]


def test_tampered_egg_is_rejected(hive: Hive) -> None:
    """Two-arm: changing any field (e.g. escalating tools or ploidy) breaks the Dufour signature."""
    egg = lay(hive, "g", "diploid", {"t": 1}, STRICT, tools=("read_file",))
    for forged in (
        replace(egg, tools=("read_file", "shell")),
        replace(egg, ploidy="haploid"),
        replace(egg, input={"t": 2}),
        replace(egg, parents=("egg_x",)),
    ):
        with pytest.raises(EggError):
            verify_egg(hive, forged)


def test_egg_signed_by_foreign_key_is_rejected(hive: Hive, tmp_path: Path) -> None:
    with Hive.init(tmp_path / "other", "o") as other:
        foreign = lay(other, "g", "haploid", {"t": 1}, {})
    with pytest.raises(EggError, match="unknown issuer"):
        verify_egg(hive, foreign)


def test_relaying_the_same_egg_is_idempotent(hive: Hive) -> None:
    egg = lay(hive, "g", "haploid", {"t": 1}, {})
    again = hive.ledger.append("egg.laid", "queen", egg.to_json(), op_id=f"egg.laid:{egg.egg_id}")
    assert again.seq == 2 and len(list(hive.ledger.events(kind="egg.laid"))) == 1
    assert TaskEgg.from_json(again.payload) == egg
