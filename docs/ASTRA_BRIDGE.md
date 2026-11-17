# Astra Bridge — v0 probe pilot (draft)

**Pilot scope.** One operator-invoked read-only probe. A dry-run witnesses GitHub-to-Astra delivery. An authenticated reply and independent readback are required to witness the return path.

## Why this exists

The GitHub connector handles issues and comments. The operator starts the probe on Astra's terminal. The probe pulls one bounded request from GitHub and can return a bounded receipt to the same issue. This tests transport before any authority is delegated for model research.

## Protocol v0

Sage creates a **public** GitHub issue in `Ceronos/Queen-OS` with exact title `ASTRA-BRIDGE-REQ: probe`, authored by the GitHub `Ceronos` account, and body consisting of `ASTRA-BRIDGE-V0` followed by one JSON object:

```text
ASTRA-BRIDGE-V0
{"protocol":"astra-bridge-v0","request_id":"astra-20261116-001","kind":"probe","expires_at":"2026-11-22T00:00:00Z"}
```

The request must be open and expire within seven days of the check. The script fetches only the supplied issue number, and the request ID must match the explicit argument. It accepts just `kind=probe` and rejects unexpected or repeated fields, other authors, pull requests, nonmatching titles, malformed payloads and HTTP redirects. The issue body supplies data for the fixed probe.

An Astra operator reviews the source and runs:

```bash
# From a checkout of the reviewed proposal:
python3 scripts/astra_bridge_probe.py --issue 32 --request-id astra-20261116-001
# After reviewing the dry-run and confirming the authorized posting identity:
gh auth status --hostname github.com
python3 scripts/astra_bridge_probe.py --issue 32 --request-id astra-20261116-001 --post
```

`--post` uses the local `gh` CLI authentication to post a bounded sanitized JSON receipt in the matching issue. Never paste an auth token into the chat, issue body, public repo or script. Run with a minimally scoped GitHub account/token; do not enable a self-hosted GitHub Actions runner on public untrusted PR code. The script is not installed as a service or cron, and does not start at boot. Owner-controlled scheduling can be considered *after* the pilot has a verified result and stronger cryptographic authorization.

The host probe reports only OS family, machine architecture, Python major.minor and coarse NVIDIA GPU model/memory (if `nvidia-smi` exists). It intentionally does not collect hostname, IP, device serial, path, environment variables, network topology or credential values. The `result_sha256` is a reproducible digest, **not an authenticity signature**. The GitHub issue comment's attributed author proves who posted the comment under GitHub's account model, not what hardware executed the code.

The default state path is `~/.local/state/queen-os/astra-bridge-v0.json`. Keep one operator-controlled state path per Astra pilot. A lock prevents concurrent posts through that path. Before posting, the script checks one bounded page of issue comments for the same request and authenticated CLI login, then rechecks the request. State is saved only after the post succeeds or an existing matching comment is observed. After a crash, inspect GitHub for the reply and confirm the process exited before removing a stale `.lock` directory. Across different state paths, accounts or hosts, deduplicate independently by `(issue_number, request_id)`. GitHub provides no atomic check-and-post operation. Invoke this once for the explicitly authorized issue.

For readback, fetch issue comments independently of the host CLI. Check the exact issue and request IDs, expected GitHub posting account, observation time against the request window, field allowlist and duplicate count. Recompute SHA-256 over the UTF-8 JSON encoding of `result` with sorted keys, ASCII escaping and separators `,` and `:` without spaces. Treat the posting account and the observed host execution as separate pieces of evidence.

## Acceptance gate before any model research

- [ ] Request issue exists and is fetched by a real Astra process.
- [ ] Local dry-run output verified by owner; no mutation.
- [ ] Local `--post` yields receipt comment in issue with same request ID.
- [ ] Sage independently reads issue comment through GitHub connector and checks its schema/hash.
- [ ] Provenance limitations and duplicate behavior recorded; then consider Ed25519-signed task manifests and a non-root, process-isolated Astra service with allowlisted task families, explicit budgets, owner-held kill switch and independent evidence review.

**Out of scope:** shell command queue, model training, repo updates, local file access, secrets transfer, persistent agent autonomy, ports/firewall changes, remote control, or auto-merge/deploy. The proposed recursive R&D program is tracked separately in #30. The bridge's purpose is to establish and measure the transport that could eventually carry *bounded* experimental task descriptions.
