# Astra Bridge — v0 probe pilot (draft)

**Research status:** source and offline tests only; no Astra execution verified. This is deliberately a one-shot bridge, not a daemon, agent runtime, unattended control plane, model training engine, or security attestation.

## Why this exists

The interactive Sage session can create GitHub issues and read issue comments, but GitHub connector access is **not** direct Thelio Astra host access. An owner-started listener on Astra can pull an explicitly bounded request from GitHub and return a bounded receipt to that same issue. That provides the first end-to-end transport witness before any authority is delegated for model research. This design does not claim continuity between ChatGPT and a local agent process.

## Protocol v0

Sage creates a **public** GitHub issue in \`Ceronos/Queen-OS\` with exact title \`ASTRA-BRIDGE-REQ: probe\`, authored by the GitHub \`Ceronos\` account, and body consisting of \`ASTRA-BRIDGE-V0\` followed by one JSON object:

\`\`\`text
ASTRA-BRIDGE-V0
{"protocol":"astra-bridge-v0","request_id":"astra-20261116-001","kind":"probe","expires_at":"2026-11-22T00:00:00Z"}
\`\`\`

The request expires no later than seven days after the listener checks it. Only \`kind=probe\` is implemented. Other keys, kind strings, actors, PRs, titles and malformed payloads fail closed. Issue contents are untrusted data, never commands. The listener reads the newest 100 open issues only; older unseen requests do not automatically run.

An Astra operator reviews the source and runs:

\`\`\`bash
# From a checked-out branch containing this proposal (not yet main):
python3 scripts/astra_bridge_probe.py              # read-only discovery, no GitHub writes
# Inspect results. If expected, authenticate gh locally with issues-comment rights.
gh auth status
python3 scripts/astra_bridge_probe.py --post       # one-shot; returns one comment per fresh request
\`\`\`

\`--post\` uses the local \`gh\` CLI authentication to post a bounded sanitized JSON receipt in the matching issue. Never paste an auth token into the chat, issue body, public repo or script. Run with a minimally scoped GitHub account/token; do not enable a self-hosted GitHub Actions runner on public untrusted PR code. The script is not installed as a service or cron, and does not start at boot. Owner-controlled scheduling can be considered *after* the pilot has a verified result and stronger cryptographic authorization.

The host probe reports only OS family, machine architecture, Python major.minor and coarse NVIDIA GPU model/memory (if \`nvidia-smi\` exists). It intentionally does not collect hostname, IP, device serial, path, environment variables, network topology or credential values. The \`result_sha256\` is a reproducible digest, **not an authenticity signature**. The GitHub issue comment's attributed author proves who posted the comment under GitHub's account model, not what hardware executed the code.

Local processed-ID state is kept at \`~/.local/state/queen-os/astra-bridge-v0.json\` only after a successful comment POST. A lost reply/ack or crash can lead to a duplicate, so treat receipts as *at least once* and deduplicate by \`(issue_number, request_id)\` when inspecting them. No background retries are scheduled. The operator can stop by simply not invoking the command again.

## Acceptance gate before any model research

- [ ] Request issue exists and is fetched by a real Astra process.
- [ ] Local dry-run output verified by owner; no mutation.
- [ ] Local \`--post\` yields receipt comment in issue with same request ID.
- [ ] Sage independently reads issue comment through GitHub connector and checks its schema/hash.
- [ ] Provenance limitations and duplicate behavior recorded; then consider Ed25519-signed task manifests and a non-root, process-isolated Astra service with allowlisted task families, explicit budgets, owner-held kill switch and independent evidence review.

**Out of scope:** shell command queue, model training, repo updates, local file access, secrets transfer, persistent agent autonomy, ports/firewall changes, remote control, or auto-merge/deploy. The proposed recursive R&D program is tracked separately in #30. The bridge's purpose is to establish and measure the transport that could eventually carry *bounded* experimental task descriptions.
