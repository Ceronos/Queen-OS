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
