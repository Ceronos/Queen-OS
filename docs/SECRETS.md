# Secrets & credentials

Queen-OS is a public repository. **No key, token, or private configuration ever goes in it.**
This file covers where keys live instead, and what stops them leaking.

## Where keys live

| Context | Location | How to set it |
|---|---|---|
| Your machine (recommended) | OS keyring: Windows Credential Manager, macOS Keychain, Linux Secret Service | `pip install "queen-os[keyring]"`, then `queen secrets set ANTHROPIC_API_KEY` |
| Your machine (no keyring) | `~/.queen-os/secrets.env` (or `$QUEEN_HOME/secrets.env`), owner-only | `queen secrets set ANTHROPIC_API_KEY` |
| Shell session | environment variable | `export ANTHROPIC_API_KEY=…` |
| GitHub CI | Repository → Settings → Secrets and variables → Actions → **New repository secret** | names: `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `GEMINI_API_KEY` |

The lookup order is environment → keyring → `secrets.env`. `queen secrets set` reads the value from
a hidden prompt, **never from a command-line argument**, because arguments end up in shell history
and process listings. `queen providers` shows each provider's key *fingerprint* (`sha256:…`), never the key.

## Enforced protections (each has a test)

- `secrets.env` is refused (for both read and write) if it is inside a git working tree, so it cannot be committed by accident.
- `secrets.env` is refused on POSIX if group or other users can read it.
- `Secret` objects never print their value (`repr`, `str`, f-strings, containers).
- Receipts and ledger events store only the key fingerprint. Before anything is persisted, the
  inference runner checks that the key bytes do not appear in the request or response, and refuses otherwise.
- Provider error messages are passed through `redact()`.
- Gemini's key goes in a header, not the URL, so logged URLs are safe.
- Vendor base-URL variables (`ANTHROPIC_BASE_URL` …) are **not** inherited. Overrides must use
  `QUEEN_<PROVIDER>_BASE_URL`, so an IDE agent's proxy setting cannot silently reroute a hive.
- CI scans every tracked file for credential shapes (`tests/test_secrets.py::test_repository_contains_no_credentials`).
- Live CI jobs get secrets only on pushes and same-repo PRs. Fork PRs never see them, and GitHub masks them in logs.

## Agents

Agents (model contexts, workers) never receive keys. Only the host-side `Inference` runner unwraps
a `Secret`, at the moment of the HTTP call. From M1 onward, tool access is granted through signed
capability tokens. A key is never part of a prompt.

## Live tests

```bash
QUEEN_LIVE_TARGETS="ollama=qwen2.5:0.5b,anthropic=claude-haiku-5-5" pytest -m live -rs
```
A target with no available key is reported **skipped**, never passed. CI always runs a real Ollama
model with no key needed. It runs hosted APIs only when their secrets are configured.
