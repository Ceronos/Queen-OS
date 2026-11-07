# Queen-OS Build Ledger

Append-only. One entry per working session. Newest at the bottom.

---

## 2026-11-07 · Session 001 · M0 substrate primitives

**Engineer:** Claude Opus 5.5 (Claude Code session `session_01H8L4suEA6LERLtdVM52b3A`)
**Owner:** Ceronos Aethrion

### Decisions (owner-approved)
- Core language: **Python ≥ 3.12**, matching the Hermes Agent baseline. Targets Windows, macOS and Linux.
- Approach: write a **build map** of the V1–V4 corpus first, then build top-down from the software core.
- Canon: the Master Thesis + Pillar docs are the latest engineering read. V1/V2 and AF-REMEDY-V1 are
  consulted for components and failure lessons. V5 = curated, non-simulated unification.

### Decisions (engineering, open to Red Team challenge)
- JCS rejects non-NFC strings instead of normalizing them, so canonicalization never mutates attested data.
- Large ints are admitted only when they equal the exact value of their canonical double text (fixed-point property).
- Ledger storage is SQLite WAL with `BEGIN IMMEDIATE` (cross-process single writer), `synchronous=FULL`.
- The fencing token is per-resource and increments on every grant. Renew keeps the token. Release expires the lease.
- The ADR-143 thresholds (mutation ≥ 98.4%, CC ≤ 5) will ship as a `sovereign` profile, not the default (see build map).
- Hermes is used as a design reference only. **No Hermes code has been ported yet**, so there is no NOTICE.

### Built (evidence: `pytest` → 56 passed locally on Linux / py3.13; CI matrix configured for 3 OS × py3.12–3.14)
| Module | Proof |
|---|---|
| `serial/jcs.py` RFC 8785 | RFC reference example, UTF-16 key-order vector, ES6 number vectors, hypothesis fixed-point + stdlib agreement |
| `serial/afser.py` AF-SER-V1 | roundtrip; two-arm: tampered read-back purges everything |
| `comb/ledger.py` | chain from GENESIS_ROOT; 6 tamper modes caught; consistent forgery caught by signatures; 4 spawn processes × 25 appends → 100-event valid chain |
| `comb/hlc.py` | monotonic under wall-clock regression |
| `comb/leases.py` | exclusion, expiry takeover (token 1→2), zombie holder rejected by fence, renew/release |
| `comb/blobs.py`, `comb/enclaves.py` | content addressing, bitrot detection, promote-only-if-unchanged, immutable committed, quarantine, 7 unsafe-name two-arm cases |
| `crypto/keys.py`, `hive.py`, `cli.py` | init/verify/tail, tamper → exit 2, swapped host key refused |

### Known limits (not defects; scheduled)
- Enclave policy is enforced in-process and with permission bits only. OS sandboxing is M3.
- On Windows, the private-key file relies on the profile ACL. Hardware keys are M3.
- The ledger is single-host. Federation (CRDT/MST) is M5.

### Open questions for owner
1. Pillar 1 Google Doc is empty (1 KB).
2. License choice.
3. Provider keys available for M1 (needs ≥ 3 lineages for the 2-of-3 quorum).

---

## 2026-11-07 · Session 001 (cont.) · License, Pillar 1, M1.3 providers

**Owner answers:** Pillar 1 has a new doc (`1cw1oEw6…`, read in full). License is proprietary, like
mainstream harnesses. Integrations should cover all major APIs plus Ollama/LM Studio. Private keys must never touch the public repo.

### Decisions
- `LICENSE`: proprietary, source-visible, all rights reserved. Hermes MIT text is kept in `NOTICE` for future ports.
  Not legal advice. The owner should have counsel review it before commercial distribution.
- Build map v0.2: Pillar 1 review table. The spec's PTP probe returns `True` when no PTP device is present,
  which breaks its own Non-Simulation Contract. Its PCR digest hashes tool stdout. Its TPM Ed25519 claim does
  not hold for most TPMs. V5 corrections are recorded there.
- Providers speak raw HTTP (no SDKs) so receipts can hash the exact wire bytes.
- Quorum lineage is keyed by **model family**, not host.
- Vendor `*_BASE_URL` variables are deliberately ignored. `QUEEN_<P>_BASE_URL` is the override.
- **"Use your API" for tests:** this Claude session has no Anthropic API key it can give to the repo,
  and must not have one. Session credentials are not transferable and would breach the no-private-keys rule.
  Live hosted-API tests read `ANTHROPIC_API_KEY` etc. from **GitHub encrypted secrets** that the owner adds.
  Until then they are reported SKIPPED. Real inference is proven today through Ollama in CI.

### Built (PR #2, stacked on #1)
| Module | Proof |
|---|---|
| `providers/` codecs ×4 + 12 OpenAI-compatible presets | codec tests against documented shapes. Every preset builds. Lineage table (13 cases). |
| `providers/receipt.py` | signed receipt, re-derivation, 5 two-arm failures (fixture in prod, forged hash, corrupted bytes, mode flip, echoed key) |
| `secrets.py` + `queen secrets` | resolution order, 0600, refusal inside a git worktree, no-print, redaction, repo-wide credential scan |
| live CI | `live / ollama`: real qwen2.5:0.5b in a production hive → answered "bee", receipt re-derived, chain verified (first run hit an Ollama registry 503; retry added, run 42369221244 green) · `live / hosted APIs`: 3 SKIPPED (no secrets yet) |

Unit suite: 89 passed. CI: 9/9 OS×Python green.

### Open
- Owner: add repository secrets `ANTHROPIC_API_KEY` (+ optional `OPENAI_API_KEY`, `GEMINI_API_KEY`), and
  optionally the variables `QUEEN_LIVE_*_MODEL`.
- Pin the Ollama version in CI. Add streaming + tool calls (M1.5).

---

## 2026-11-07 · Sage/Codex · CI authorization boundary

**Scope:** owner-requested separation of offline contribution checks from explicitly authorized live inference. Stacked on the existing M1 provider branch; no live workflow was dispatched, model contacted, credential accessed or repository environment/secret configured.

- Ordinary push/PR CI contains only the cross-platform offline matrix, with explicit live-directory/marker exclusion and no mapped model keys or inference commands.
- Live inference moves to a separate manual workflow, exact approved main SHA/provider/model/one-request scope, and an existing environment requiring reviewers with self-review prevention. Configuration is checked before setup and again after approval.
- An authorization URL is a pointer for the actual reviewer, not verified containment evidence. Environment configuration is not created by this contribution and does not clear a research NO-GO.
- Validation: baseline **89 offline tests passed**; with the new dispatch-gate tests **110 passed** on Linux / Python 3.12.3. Ruff and formatting passed; mypy passed for the 21 package modules and the gate script. CLI hive init and signed-chain verification passed before changes. YAML trigger/job structure was parsed and inspected. Other OS CI results remain pending.
- Initial baseline: 87 passed and two fixture credential-file tests refused the default temp path because it was inside a Git worktree. Repeating in a fresh non-Git temporary directory passed all 89; the production credential check was not weakened.
- Limits: no proof of live provider behavior, billing, process containment or independent security acceptance. Optional Ollama installation pinning remains separate work.

Agent: Sage (Codex)
Codex-Session: 01a1ab22-a4f2-7852-b510-5973fd1a4952

---

## 2026-11-07 · Sage/Codex · Offline ledger recovery contracts

**Scope:** owner-requested contribution after the separate CI safeguard (PR #3), stacked on its exact commit `174f36a95473201c5717725ac42140fa05a1fd8f`. No production source, live inference, runtime settings or service changes.

- Added five offline cases: lease/event rollback after both INSERTs under RuntimeError and KeyboardInterrupt; committed append surviving failed post-write readback; expired/superseded fence rejection across clean reopen; invalid payload rejection preserving sequence/lease with regressed-clock restart. Generated local keys, real SQLite and signature verification; work payloads are fixtures.
- A post-commit caller exception leaves a discoverable committed effect. The contract requires stored-evidence reconciliation before retry; a payload operation ID does not itself enforce uniqueness. No automatic retry or exactly-once claim was added.
- Local validation: **115 offline tests passed**, versus 110 before this contribution. Ruff/format and package mypy passed on Linux / Python 3.12.3. The CI safeguard's nine OS/Python jobs passed in run 42370239866; this contribution's own cross-platform checks remain to be observed.
- Limits: injected Python exceptions and clean connection reopen are not process-kill/power-loss tests, actor authorization, OS containment or independent acceptance. The research NO-GO is unchanged. See `docs/RECOVERY_CONTRACT.md` for reproduction and remaining implementation contracts.
- Next: review the CI safeguard first, then these tests; continue TaskEgg/capability/worker integration against the existing store, with explicit uncertain-effect and idempotency contracts before retries.

Agent: Sage (Codex)
Codex-Session: 01a1ab22-a4f2-7852-b510-5973fd1a4952
