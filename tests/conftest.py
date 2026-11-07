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


def _has_git_ancestor(path: Path) -> bool:
    return any((p / ".git").exists() for p in [path, *path.parents])


@pytest.fixture
def cred_home(tmp_path: Path):
    """A writable directory with no git ancestor (QOS-0002).

    The credential store correctly refuses to write secrets inside a git working tree. On hosts
    whose temp dir sits in a repo, fall back to $QUEEN_TEST_TMP, then the system temp root.
    """
    import shutil
    import tempfile

    if not _has_git_ancestor(tmp_path):
        yield tmp_path
        return
    for base in (os.environ.get("QUEEN_TEST_TMP"), tempfile.gettempdir(), str(Path.home())):
        if base and Path(base).is_dir() and not _has_git_ancestor(Path(base).resolve()):
            d = Path(tempfile.mkdtemp(prefix="qos-cred-", dir=base))
            try:
                yield d
            finally:
                shutil.rmtree(d, ignore_errors=True)
            return
    pytest.skip("no writable temp directory outside a git worktree; set QUEEN_TEST_TMP")
