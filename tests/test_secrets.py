from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from queen_os.secrets import Secret, SecretError, SecretStore, find_secrets, redact

FAKE_ANTHROPIC = "sk-" + "ant-" + "api03-" + "A" * 40  # built at runtime so the repo scan stays clean
FAKE_GOOGLE = "AI" + "za" + "B" * 35


def test_secret_never_prints_its_value() -> None:
    s = Secret(FAKE_ANTHROPIC, "env:X")
    for rendering in (repr(s), str(s), f"{s}", repr([s]), repr({"k": s})):
        assert FAKE_ANTHROPIC not in rendering
    assert s.fingerprint.startswith("sha256:") and s.reveal() == FAKE_ANTHROPIC


def test_redact_scrubs_known_shapes_and_explicit_secrets() -> None:
    custom = Secret("hunter2-local-proxy-token")
    text = f"key={FAKE_ANTHROPIC} g={FAKE_GOOGLE} proxy=hunter2-local-proxy-token"
    out = redact(text, [custom])
    assert FAKE_ANTHROPIC not in out and FAKE_GOOGLE not in out and "hunter2" not in out
    assert len(find_secrets(text)) == 2


def test_resolution_order_env_then_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    store = SecretStore(tmp_path / "home")
    assert store.get("ANTHROPIC_API_KEY") is None
    store.set("ANTHROPIC_API_KEY", "from-file")
    got = store.get("ANTHROPIC_API_KEY")
    assert got is not None and got.reveal() == "from-file" and got.source == "file:secrets.env"
    monkeypatch.setenv("ANTHROPIC_API_KEY", "from-env")
    got = store.get("ANTHROPIC_API_KEY")
    assert got is not None and got.reveal() == "from-env"
    if sys.platform != "win32":
        assert (store.file.stat().st_mode & 0o777) == 0o600
    store.delete("ANTHROPIC_API_KEY")
    assert store.names() == []


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX permission bits")
def test_group_readable_secrets_file_fails_closed(tmp_path: Path) -> None:
    store = SecretStore(tmp_path)
    store.set("OPENAI_API_KEY", "v")
    os.chmod(store.file, 0o644)
    with pytest.raises(SecretError):
        store.get("OPENAI_API_KEY")


def test_secrets_file_inside_git_worktree_is_refused(tmp_path: Path) -> None:
    """Two-arm: a secrets file that could be committed must never be written or read."""
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    store = SecretStore(repo / ".queen")
    with pytest.raises(SecretError):
        store.set("OPENAI_API_KEY", "v")
    assert not (repo / ".queen" / "secrets.env").exists()
    (repo / ".queen").mkdir(exist_ok=True)
    (repo / ".queen" / "secrets.env").write_text("OPENAI_API_KEY=planted\n")
    if sys.platform != "win32":
        os.chmod(repo / ".queen" / "secrets.env", 0o600)
    with pytest.raises(SecretError):
        store.get("OPENAI_API_KEY")


def test_missing_required_key_explains_setup_without_leaking(tmp_path: Path) -> None:
    with pytest.raises(SecretError, match="queen secrets set ANTHROPIC_API_KEY"):
        SecretStore(tmp_path).require("ANTHROPIC_API_KEY")


def test_repository_contains_no_credentials() -> None:
    """Every tracked file is scanned for credential shapes. CI fails if one is committed."""
    root = Path(__file__).resolve().parents[1]
    try:
        tracked = subprocess.run(["git", "ls-files", "-z"], cwd=root, check=True, capture_output=True).stdout
        files = [root / f for f in tracked.decode().split("\0") if f]
    except (OSError, subprocess.CalledProcessError):
        files = [p for p in root.rglob("*") if p.is_file() and ".git" not in p.parts]
    hits = {}
    for path in files:
        try:
            found = find_secrets(path.read_text(encoding="utf-8"))
        except (UnicodeDecodeError, OSError):
            continue
        if found:
            hits[str(path.relative_to(root))] = found
    assert hits == {}
