from __future__ import annotations

import contextlib
import os
import stat
from pathlib import Path

import pytest


@pytest.fixture
def tmp_path(tmp_path: Path):  # noqa: F811 - wrap the builtin so read-only files don't break cleanup on Windows
    yield tmp_path
    for root, dirs, files in os.walk(tmp_path):
        for name in dirs + files:
            p = Path(root) / name
            with contextlib.suppress(OSError):
                os.chmod(p, stat.S_IWRITE | stat.S_IREAD | (stat.S_IEXEC if p.is_dir() else 0))


@pytest.fixture(autouse=True)
def _isolate_credentials(monkeypatch: pytest.MonkeyPatch, tmp_path_factory: pytest.TempPathFactory) -> None:
    """Unit tests never touch the developer's keyring, home directory or real API keys."""
    monkeypatch.setenv("QUEEN_DISABLE_KEYRING", "1")
    monkeypatch.setenv("QUEEN_HOME", str(tmp_path_factory.mktemp("queen_home")))
    for var in list(os.environ):
        if var.endswith("_API_KEY") and not os.environ.get("QUEEN_LIVE"):
            monkeypatch.delenv(var)
