from __future__ import annotations

from pathlib import Path

import pytest

from queen_os.hive import Hive
from queen_os.queen.egg import lay
from queen_os.queen.valve import UNKNOWN_TOOL_RISK, ValveRefusal, profile_for, tool_risk

STRICT = {"type": "object", "properties": {"a": {"type": "string"}}, "required": ["a"]}
LOOSE_OBJECT = {"type": "object", "properties": {"a": {"type": "string"}}}  # no "required"


@pytest.fixture
def hive(tmp_path: Path):  # type: ignore[no-untyped-def]
    with Hive.init(tmp_path / "h", "v") as h:
        yield h


@pytest.mark.parametrize(
    ("tool", "risk"),
    [
        ("read_file", 0.1),
        ("write_file", 0.6),
        ("delete_branch", 0.9),
        ("shell", 0.95),
        ("exec_cmd", 0.95),
        ("web_fetch", 0.4),
        ("brand_new_tool", UNKNOWN_TOOL_RISK),
    ],
)
def test_tool_risk_table_and_unknown_fails_closed(tool: str, risk: float) -> None:
    assert tool_risk(tool) == risk


def test_read_only_haploid_stays_exploratory(hive: Hive) -> None:
    p = profile_for(lay(hive, "g", "haploid", {"q": 1}, {}, tools=("read_file",)))
    assert (p.ploidy, p.temperature, p.quorum, p.escalated, p.strict_schema) == ("haploid", 0.9, 0, False, False)


def test_diploid_floor_even_without_risky_tools(hive: Hive) -> None:
    p = profile_for(lay(hive, "g", "diploid", {"q": 1}, STRICT))
    assert p.ploidy == "diploid" and p.risk == 0.5 and p.temperature <= 0.2 and p.max_calls == 1


def test_risky_haploid_is_escalated(hive: Hive) -> None:
    """Two-arm: an egg can't lower its own risk by declaring itself haploid."""
    p = profile_for(lay(hive, "g", "haploid", {"q": 1}, STRICT, tools=("write_file",)))
    assert p.ploidy == "diploid" and p.escalated and p.temperature <= 0.2


@pytest.mark.parametrize("schema", [{}, LOOSE_OBJECT])
def test_escalated_egg_without_strict_schema_is_refused(hive: Hive, schema: dict) -> None:  # type: ignore[type-arg]
    egg = lay(hive, "g", "haploid", {"q": 1}, schema, tools=("write_file",))
    with pytest.raises(ValveRefusal, match="requires diploid"):
        profile_for(egg)


def test_high_risk_requires_cross_lineage_quorum(hive: Hive) -> None:
    p = profile_for(lay(hive, "g", "diploid", {"q": 1}, STRICT, tools=("read_file", "shell")))
    assert p.risk == 0.95 and p.quorum == 2 and p.temperature == 0.0
