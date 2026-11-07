"""Live inference tests. Never run by default (`-m 'not live'` in pyproject).

Targets come from QUEEN_LIVE_TARGETS, e.g. "ollama=qwen2.5:0.5b,anthropic=claude-haiku-5-5".
Keys come only from the environment (CI encrypted secrets) or the user's OS keyring.
"""

from __future__ import annotations

import os

import pytest


@pytest.fixture(autouse=True)
def _isolate_credentials(monkeypatch: pytest.MonkeyPatch, tmp_path_factory: pytest.TempPathFactory) -> None:
    """Override the unit-test isolation: live tests may read real keys and the keyring."""
    monkeypatch.setenv("QUEEN_HOME", os.environ.get("QUEEN_HOME") or str(tmp_path_factory.mktemp("queen_home")))


def pytest_generate_tests(metafunc: pytest.Metafunc) -> None:
    if "target" in metafunc.fixturenames:
        spec = os.environ.get("QUEEN_LIVE_TARGETS", "")
        targets = [tuple(t.split("=", 1)) for t in spec.split(",") if "=" in t]
        if targets:
            metafunc.parametrize("target", targets, ids=[f"{p}:{m}" for p, m in targets])
        else:
            metafunc.parametrize("target", [pytest.param(None, marks=pytest.mark.skip("QUEEN_LIVE_TARGETS unset"))])
