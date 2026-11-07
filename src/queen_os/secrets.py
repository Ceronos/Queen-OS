"""Credential custody (the Tripartite Authority "Resource Custody" branch).

Rules this module enforces:

* Keys are never in the repository. Resolution order: process environment →
  OS keyring (optional ``keyring`` package) → ``$QUEEN_HOME/secrets.env``.
* ``secrets.env`` must be owner-only (POSIX ``0600``) and must not be inside a git
  working tree. Either violation fails closed.
* A key is held in a :class:`Secret`, whose ``repr``/``str`` never show the value.
  Ledgers and receipts record only its fingerprint.
* Agents (model contexts) never receive keys. Only the host-side inference runner unwraps them.
* :func:`redact` scrubs known secret shapes from any text before it is logged or stored.
"""

from __future__ import annotations

import contextlib
import hashlib
import os
import re
import sys
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

KEYRING_SERVICE = "queen-os"

_SECRET_PATTERNS = [
    re.compile(p)
    for p in (
        r"sk-ant-[A-Za-z0-9_\-]{16,}",
        r"sk-(?:proj-|or-v1-)?[A-Za-z0-9_\-]{20,}",
        r"AIza[0-9A-Za-z_\-]{35}",
        r"gsk_[A-Za-z0-9]{20,}",
        r"xai-[A-Za-z0-9]{20,}",
        r"gh[pousr]_[A-Za-z0-9]{30,}",
        r"github_pat_[A-Za-z0-9_]{40,}",
        r"AKIA[0-9A-Z]{16}",
        r"-----BEGIN [A-Z ]*PRIVATE KEY-----",
    )
]


class SecretError(PermissionError):
    pass


@dataclass(frozen=True)
class Secret:
    """An opaque credential. ``reveal()`` is the only way to read the value."""

    _value: str = field(repr=False)
    source: str = "unknown"

    def reveal(self) -> str:
        return self._value

    @property
    def fingerprint(self) -> str:
        return "sha256:" + hashlib.sha256(self._value.encode()).hexdigest()[:12]

    def __repr__(self) -> str:
        return f"Secret({self.fingerprint}, source={self.source})"

    __str__ = __repr__


def redact(text: str, extra: Iterable[Secret] = ()) -> str:
    for secret in extra:
        if secret.reveal():
            text = text.replace(secret.reveal(), f"[REDACTED {secret.fingerprint}]")
    for pattern in _SECRET_PATTERNS:
        text = pattern.sub("[REDACTED]", text)
    return text


def find_secrets(text: str) -> list[str]:
    """Credential-shaped substrings (truncated). Overlapping pattern hits count once."""
    spans: dict[int, str] = {}
    for pattern in _SECRET_PATTERNS:
        for m in pattern.finditer(text):
            spans.setdefault(m.start(), m.group(0)[:12] + "…")
    return [spans[k] for k in sorted(spans)]


def _inside_git_worktree(path: Path) -> bool:
    return any((parent / ".git").exists() for parent in [path.parent, *path.parent.parents])


def _parse_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        values[key.strip()] = value
    return values


class SecretStore:
    def __init__(self, home: Path) -> None:
        self.home = home
        self.file = home / "secrets.env"

    # -- resolution ---------------------------------------------------------------

    def get(self, env_var: str) -> Secret | None:
        value = os.environ.get(env_var)
        if value:
            return Secret(value, f"env:{env_var}")
        value = self._keyring_get(env_var)
        if value:
            return Secret(value, "keyring")
        file_values = self._read_file()
        if file_values.get(env_var):
            return Secret(file_values[env_var], f"file:{self.file.name}")
        return None

    def require(self, env_var: str) -> Secret:
        secret = self.get(env_var)
        if secret is None:
            raise SecretError(
                f"{env_var} is not set. Run `queen secrets set {env_var}` or export it in your shell; never commit it."
            )
        return secret

    # -- storage ------------------------------------------------------------------

    def set(self, env_var: str, value: str, prefer_keyring: bool = True) -> str:
        if not re.fullmatch(r"[A-Z][A-Z0-9_]{1,63}", env_var):
            raise ValueError(f"invalid secret name {env_var!r}")
        if prefer_keyring and self._keyring_set(env_var, value):
            return "keyring"
        values = self._read_file()
        values[env_var] = value
        self._write_file(values)
        return f"file:{self.file}"

    def delete(self, env_var: str) -> None:
        self._keyring_delete(env_var)
        values = self._read_file()
        if values.pop(env_var, None) is not None:
            self._write_file(values)

    def names(self) -> list[str]:
        return sorted(self._read_file())

    # -- file backend -------------------------------------------------------------

    def _check_file(self) -> None:
        if _inside_git_worktree(self.file.resolve()):
            raise SecretError(f"{self.file} is inside a git working tree; refusing to use it for secrets")
        if sys.platform != "win32" and self.file.stat().st_mode & 0o077:
            raise SecretError(f"{self.file} is readable by group/other; run chmod 600")

    def _read_file(self) -> dict[str, str]:
        if not self.file.exists():
            return {}
        self._check_file()
        return _parse_env_file(self.file)

    def _write_file(self, values: dict[str, str]) -> None:
        self.home.mkdir(parents=True, exist_ok=True)
        if _inside_git_worktree(self.file.resolve()):
            raise SecretError(f"{self.file} is inside a git working tree; refusing to write secrets there")
        tmp = self.file.with_suffix(".tmp")
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | getattr(os, "O_BINARY", 0), 0o600)
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as fh:
            fh.write("# Queen-OS secrets. Owner-only. Never commit.\n")
            for key in sorted(values):
                fh.write(f"{key}={values[key]}\n")
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, self.file)
        if sys.platform != "win32":
            os.chmod(self.file, 0o600)

    # -- keyring backend (optional dependency) ------------------------------------

    @staticmethod
    def _keyring() -> Any:
        if os.environ.get("QUEEN_DISABLE_KEYRING"):
            return None
        try:
            import keyring  # type: ignore[import-not-found,unused-ignore]
            from keyring.backends import fail  # type: ignore[import-not-found,unused-ignore]
        except ImportError:
            return None
        if isinstance(keyring.get_keyring(), fail.Keyring):
            return None
        return keyring

    def _keyring_get(self, name: str) -> str | None:
        kr = self._keyring()
        if kr is None:
            return None
        try:
            value = kr.get_password(KEYRING_SERVICE, name)
        except Exception:  # noqa: BLE001 - a locked/broken keyring must not crash resolution
            return None
        return str(value) if value else None

    def _keyring_set(self, name: str, value: str) -> bool:
        kr = self._keyring()
        if kr is None:
            return False
        try:
            kr.set_password(KEYRING_SERVICE, name, value)
        except Exception:  # noqa: BLE001
            return False
        return True

    def _keyring_delete(self, name: str) -> None:
        kr = self._keyring()
        if kr is None:
            return
        with contextlib.suppress(Exception):  # an absent entry is fine
            kr.delete_password(KEYRING_SERVICE, name)
