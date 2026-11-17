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

## Explicit connector return relay (candidate, stacked on #35)

`scripts/astra_bridge_return.py` closes the credential gap with an **operator-mediated**
relay. It prepares a bounded local probe envelope and independently checks its GitHub
readback. It never posts, starts a service, calls a model, dispatches jobs, installs
credentials, or changes Queen-OS authority. This is a narrow pilot of the build map's
messaging-gateway row, not a general gateway or authenticated autonomous Sage runtime.

```bash
python scripts/astra_bridge_return.py prepare --issue 32 \
  --request-id astra-20261116-001 \
  --handoff-marker SAGE-BRIDGE-20261117-194755Z --output receipt.txt
# Review the exact receipt and public destination before the explicit connector post.
# Independently read existing comments first; reconcile an uncertain post before retrying.
python scripts/astra_bridge_return.py verify --issue 32 \
  --request-id astra-20261116-001 --receipt receipt.txt
# A receiving operator/session may explicitly post the exact ACK emitted by verify.
python scripts/astra_bridge_return.py verify-ack --issue 32 \
  --request-id astra-20261116-001 --receipt receipt.txt
```

The export exclusively creates its output file. Preserve that file as the expected
message; do not regenerate a new observation when recovering an uncertain delivery.
The relay permits only the original bounded probe fields, binds the exact request-body
SHA-256, issue, request ID, handoff marker and both local script SHA-256 values, and
states `probe-receipt-only; real-agent NO-GO`. Source digests identify the local files
observed by the preparing process; they do not prove execution of those bytes.

The expected public posting account is pinned to both `Ceronos` and GitHub user ID
`202629591`. That is the existing connected account, **not a separate Sage identity**.
Readback uses the fixed public GitHub HTTPS endpoint with redirects disabled, one page
of at most 100 comments, and the original probe's response/time limits. It requires
exact expected bytes, issue URL, account ID/login, an unedited comment and exactly one
matching receipt. The acknowledgment binds the full receipt-body SHA-256 and the
GitHub receipt comment ID. Modified, missing, duplicate or conflicting messages fail
closed. Unknown payload fields and duplicate JSON keys fail closed. Active-request
validation is required even for verification; after expiry or closure, retain evidence
and reconcile manually rather than reopening or extending a request automatically.

**Idempotency boundary:** repeating verification performs reads only. Reuse the same
export and inspect GitHub after a timeout; an existing exact comment means delivery
already happened and must not be repeated. Duplicate comments are a conflict, never a
second success. The relay has no automated retry or posting loop. GitHub has no atomic
compare-and-post operation, so multiple operators/accounts/state paths cannot be given
an exactly-once guarantee. Keep one authorized writer for the pilot. The original
`--post` path retains its local lock; neither path authenticates hardware or model
identity. Never count a same-account ACK as independent model review.

The earlier `SAGE-BRIDGE-20261117-194755Z` acknowledgment was independently recovered
from the designated Sage Metacognitive Engine chat: user message
`8336c02a-7d99-43e9-a68a-2cca20e13910`, acknowledgment
`cc3c67be-f1a2-43b1-8bbd-3f1ea854ee19`, and later continuity incorporation
`9dc8cb97-2872-430c-88e2-934750d50ecf`. Those are app-retrieved conversation records,
not cryptographic attestations or proof of scheduled connector inheritance.

Current candidate evidence: 36 new fixture-only relay cases plus the existing 16 probe
cases pass locally. A real local `prepare` read issue #32 and produced a sanitized
receipt; public posting was blocked by automatic approval review pending explicit
owner approval for that payload/destination. No new GitHub receipt/ACK or fresh Sage
readback has been demonstrated. The original #35 report/CI and the recovered historical
handoff remain separate evidence. Independent review, verified signatures, exact-head
CI, owner integration approval, real-agent containment acceptance and fresh-session
adapter qualification remain required. No merge, deployment, scheduler edit, budget
reset or frozen-lab change is authorized by this protocol.
