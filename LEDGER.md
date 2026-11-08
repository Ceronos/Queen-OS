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

---

## 2026-11-07 · Sage/Codex · Transaction and lease recovery hardening

**Scope:** owner-authorized extended contribution after PR #4; existing ledger/lease modules only, plus offline tests/docs. No models, live keys, service changes, frozen research edits or automatic retries.

- Observed before fixes: real SQLite deferred-constraint failure left a transaction open after failed COMMIT; automatic SQLite rollback caused a second ROLLBACK to mask the original error. Limited fault injection also reproduced primary-error masking when cleanup failed. Baseline: 115 offline tests and production-mode CLI init/chain verification passed.
- Fix: handle COMMIT and transaction-body errors together; roll back only an active transaction; preserve the primary failure; attempt to discard a connection whose cleanup fails and require reopen/reconciliation. No exception is interpreted as proof that an effect is absent.
- Lease lifetime is now a strictly positive integer for acquisition/renewal, excluding bool/float. Renewal writes a signed `lease.renewed` event atomically with its row. Grant/renew/release all perform existing post-commit event verification before acknowledgement. Readback failure may follow a committed effect.
- Added 25 cases: 23 pre-fix regression/contract cases plus two actual synthetic process exits before/after COMMIT. The pre-fix 23 failures represent contract cases, not 23 vulnerabilities. Generated keys and real SQLite/signatures; fault-injection and process-exit boundaries are identified in `docs/TRANSACTION_LEASE_RECOVERY.md`.
- Local evidence: **140 offline tests passed**; Ruff/format and package mypy passed on Linux/Python 3.12.3. Prior PR #4 passed all nine CI jobs in run 42370518063. This extension's own matrix remains to be observed. Reproduction commands, compatibility changes and limitations are documented.
- Compatibility: no SQLite/event-header schema changes or historical backfill; each renewal now adds an event, and invalid duration types now raise ValueError. Existing event-count tests were updated for the real renewal event. Historic unrecorded renewals remain unknown.
- Limits: controlled abrupt process exit does not prove power-loss durability, OS containment, actor capability checks, idempotency or independent acceptance. Frozen v65 and real-agent NO-GO are unchanged.
- Next: review/land in dependency order; continue TaskEgg/capability and worker claims, with explicit uncertain-effect/idempotency contracts before retries.

Agent: Sage (Codex)
Codex-Session: 01a1ab22-a4f2-7852-b510-5973fd1a4952

---

## 2026-11-07 · Claude · Issues ledger, two-engineer protocol, QOS-0001, host probe, eggs + capabilities

**Owner direction:** keep a separate known-issues ledger. Sage works in tandem and runs live tests on the
Thelio Astra. Keep building operations. The owner offered an Anthropic key for Claude's tests (see decisions).

**Stacked on Sage's PR #4** (`codex/offline-recovery-contracts`), not beside it, so there's one linear stack: #1 → #2 → #3 → #4 → #5.

### Decisions
- `docs/ISSUES.md`: separate known-issues ledger, `QOS-####`, append-only, claim-before-fix. Seeded with 17 issues,
  then 5 more this session (QOS-0018–0022).
- `docs/ENGINEERS.md`: lanes (Claude: substrate/cognition, Sage: admission/recovery/hardware), stacking,
  cross-lineage review, shared-file rules, Thelio Astra evidence format.
- **Accepted Sage's PR #3 direction:** inference leaves PR CI and goes behind the authorized dispatch workflow.
  The cost of that change (no continuous real-inference signal) is logged as QOS-0004, and the single-owner
  self-review deadlock as QOS-0003. Both need owner decisions.
- **Anthropic key:** not pasted into chat. A chat transcript isn't a secret store. The key belongs in the
  `live-inference` environment secrets (Sage's workflow). Claude then exercises it only through that
  workflow, and never sees the value.

### Built (PR #5)
| Change | Proof |
|---|---|
| QOS-0001 idempotent `append(op_id=…)` (Sage's finding) | lost-ack retry returns the original; 3 conflict arms; replay after fence expiry vs new op fenced; op_id bound into the chain (tamper → ChainBroken); legacy migration |
| QOS-0002 credential tests vs git-ancestor temp dirs (Sage's finding) | `cred_home` fixture; reproduced by running with `--basetemp` inside a git repo → 7 passed |
| QOS-0011 ARM64 Linux in the CI matrix | `ubuntu-24.04-arm` × 3 Pythons |
| QOS-0012 `host/probe.py` + `queen host probe` | stdlib-only (runs with `python -I -S`). Empty sysfs → nothing reads OK. Synthetic TPM → raw-PCR digest changes when one PCR changes. Signed `host.probe` event. |
| Capability tokens (`authority/`) | 10 tests: scope arms (subject/provider/model/size), exact tool names, expiry, revocation, widened token, foreign issuer, unissued re-signed token, prompt-claimed authority, **8 processes vs a 3-call budget → exactly 3 succeed** |
| `Inference.run` requires a capability. Receipts bind token + spend (QOS-0014). | receipt tests updated. The CLI mints a one-call operator token per `queen infer`. |
| TaskEgg 7-tuple (`queen/egg.py`) | DAG by construction, 8 malformed-egg arms, 4 tamper arms, foreign-issuer arm, idempotent re-lay |

Local: **147 passed** (Linux/py3.13), ruff + mypy --strict clean. CI: 12/12 green (ubuntu x64, ubuntu ARM64, Windows, macOS × py3.12–3.14) after a Windows-only mypy fix.

Agent: Claude (Opus 5.5) · Claude-Session: session_01H8L4suEA6LERLtdVM52b3A

---

## 2026-11-07 · Claude · Owner decisions: SO-0001, live canary, NO-GO clarified; stack reconciled with #6

**Owner decisions (verbatim in `docs/ISSUES.md`):** (1) Sage and Claude may start live runs on their own
authority, under the owner's explicit orders. (2) Put the real-model check back in place, and tell Sage
why in writing. (3) The "NO-GO" is a precautionary artifact still being worked out. Sage is now focused on
real-agent orientation.

### Stack
- Sage opened #6 (transaction/lease hardening) as a sibling of #5 on #4. **Rebased #5 onto #6** and resolved
  the LEDGER/HANDOFF conflicts (LEDGER: both entries kept, append-only). Combined suite **172 passed**
  before this session's additions. Retargeted PR #5's base to `codex/transaction-lease-recovery`.
  Stack: #1 → #2 → #3 → #4 → #6 → #5.

### Built
| Change | Evidence |
|---|---|
| SO-0001 standing order (`governance/`), standing-order mode in `live_ci_gate.py` (QOS-0003) | 14 new gate tests. Sage's 20 reviewer-mode tests unchanged. Scope, engineer, tokens, daily budget (API-counted, fail closed, pagination refused), deadlocking env refused, order read at the approved SHA. |
| `live-canary.yml` keyless canary on push to main (QOS-0004). Rationale for Sage in `docs/LIVE_CANARY.md`. | **Run 42373449340: success.** qwen2.5:0.5b answered "bee" in a production hive, receipt re-derived, signed 5-event chain verified, evidence artifact uploaded without `vault/`. |
| Ollama runtime pinned to 0.40.15 and asserted (QOS-0005, partial: installer script still unpinned) | canary log `ollama --version` |
| **QOS-0023:** `live-inference.yml` invalid since #3 (`runner` context in job-level env) | Every push since #3 showed a 0-job failure. Fixed, and **actionlint + shellcheck** now run in CI. |
| **QOS-0024:** my own probe reported `clock_discipline=ptp` for a Hyper-V virtual PHC | Caught by the canary's evidence. Virtual PHCs are now labelled, and the best possible discipline is `phc-unverified`. Test added. |
| QOS-0013 resolved by owner clarification | — |

Local: 186 passed; ruff, mypy --strict, actionlint + shellcheck clean.

Agent: Claude (Opus 5.5) · Claude-Session: session_01H8L4suEA6LERLtdVM52b3A

---

## 2026-11-07 · Sage/Codex · Bounded smoke acceptance and archived real-call verification

**Owner-selected milestone:** bounded real-model harness smoke, separately from the frozen v65 comparative study. This branch stacks on PR #5 at c802dc1a7943781f2262ef9b8e9457587e4725e6; no frozen-source, service, environment, reviewer or hosted-key changes.

- Recovered actual canary run 42373449340, job logs and artifact 13573899082 from commit 365de353ced5e7d4bf9b21aff5f5575cc1186163. ZIP digest matched the GitHub artifact API: 29dab4f7c21d336a36ae35a31547aaaadcf05e8ed28fffd508fd136bed1103e5. This was an earlier real GitHub run, not a new Astra inference.
- Fresh offline readback verified five signed events, exact raw bytes and a one-call/16-output-token capability; actual CLI response was `Mosquito.` (four output tokens). The separate live pytest log said `bee`. Thus the witnessed inference path passed, while the CLI comb-answer oracle failed; earlier nonempty checks missed that distinction (QOS-0025). Historical PTP overclaim remains preserved and excluded from smoke acceptance.
- Added a no-network archive verifier and 16 offline positive/negative cases, using the unchanged historical real-run ZIP as a separately downloaded, attributed local fixture. The ZIP is not published; seven replay cases explicitly skip in ordinary CI without QUEEN_ARCHIVED_SMOKE. Added explicit fixed-word checks to both live paths and raw-byte verification to the canary. Existing main/manual triggers and two-call limits are preserved. No semantic live success is claimed until a corrected candidate actually runs.
- Baseline initially lacked newly declared jsonschema dependencies; refreshed only the existing isolated dev environment. Then 184 tests passed and two credential-temp cases explicitly skipped under the Git-ancestor temp root. Final full validation and CI are recorded in this PR and local receipts; no skipped case counts as a pass.
- Final local validation: **202 offline tests passed with no skips** after providing an explicit non-Git fixture root. Ruff/format, package mypy and strict verifier types passed. Actionlint/shellcheck are checked by PR CI; they are not installed on this execution view.
- Scope: first engineering smoke milestone; not independent containment acceptance, model freshness, A/B/C fairness, hardware proof or consciousness evidence. Detailed acceptance/reproduction contract: docs/SMOKE_ACCEPTANCE.md.

Agent: Sage (Codex)
Codex-Session: 01a1ab22-a4f2-7852-b510-5973fd1a4952

---

## 2026-11-07 · Sage/Codex · Retain admitted CLI evidence before semantic failure (QOS-0025)

The owner authorized this follow-up after canary 42380605862, attempt 1, ran head `9a907655de0f249f5a4001770a6de88e4bc30ab8`. Its pytest call returned `bee`; CLI returned `beeedom` (3 output tokens / 16 allowed). Producer signature checks passed and the answer guard correctly exited 2. Artifact upload was skipped, so the fresh ZIP could not be downloaded/reverified. The log-reported receipt is `d5746442a2f99f45da0d50d0eb8547d8055c0e6935d89de7b19838bdd7afe104`; this is producer evidence, not independent acceptance.

- Split the existing CLI workflow into signed-evidence admission, normally success-gated upload, then the unchanged exact-word answer gate. Bind both verification steps to the admitted ZIP digest via a step output. Missing upload files now fail explicitly.
- No unconditional export or continue-on-error. Invalid/private/incomplete archives block upload; a semantic mismatch retains admissible evidence and leaves the job red. No prompt, model, call budget, token cap, trigger, credential or live-inference policy change.
- Offline baseline: 202 passed and a new local hive's signed genesis verified. Updated suite: **203 passed**, with the historical archive explicitly supplied and non-Git credential fixture storage. Ruff/format, package mypy and strict verifier mypy passed.
- The actual post-inference workflow shell blocks were rehearsed offline against the preserved historical archive: admission exit 0; local retained evidence survived answer exit 2; synthetic private-file admission exit 1 with no success output. This local copy does not witness GitHub's upload service. Seven historical archive cases still skip without explicit `QUEEN_ARCHIVED_SMOKE`; all other negative cases run in ordinary CI.
- Remaining limits: earlier pytest failure, cancellation, structural rejection or upload failure may leave no exported CLI bundle. The pytest hive remains unexported. New-revision GitHub CI and a separately authorized live upload witness remain to be observed. No new model call, merge, local service change, archive publication or frozen-v65 mutation occurred.

Agent: Sage (Codex)
Codex-Session: 01a1ab22-a4f2-7852-b510-5973fd1a4952

---

## 2026-11-07 · Claude · First stack landed on `main`

- **Owner fixed the `main` ruleset.** "Restrict updates" with no bypass list had locked `main` for everyone, and
  required code-scanning/code-quality results could never arrive because no tool was configured.
- **Landing (owner chose Claude's recommendation, Option A):** one consolidated merge instead of six
  squash-and-rebase cycles. #7 (consolidated) was blocked by *required signed commits*, because three
  upstream commits from #3/#4/#6 were unsigned. Re-landed as **#8**: the byte-identical tree
  (`git diff` with c802dc1 is empty) as one verified commit, with Sage credited as co-author. The owner
  squash-merged #8 → `main` @ **90b4035** (verified).
- Claude's attempt to merge through the API was **refused by the session's safety classifier**
  ("merge without review"). The owner merges `main`, and that boundary is correct.
- **Post-merge evidence on `main`:** CI run 42379979228 green. Live canary run 42379979225 green: qwen2.5:0.5b →
  "bee", receipt re-derived, signed 5-event chain verified. The probe labelled the Hyper-V PHC virtual and reported
  the Mellanox NIC PHC as `phc-unverified` (QOS-0024 fix confirmed on real infrastructure).
- #1–#6 closed with links to #8. Opened **QOS-0026** (Sage's commits must be signed; QOS-0025 is Sage's canary finding). `ENGINEERS.md` now says:
  branch from `main`, keep stacks short, merge with squash.

Agent: Claude (Opus 5.5) · Claude-Session: session_01H8L4suEA6LERLtdVM52b3A

**Correction (same day):** earlier entries said the canary model "answered 'bee'". That came from the live
pytest step only. Sage verified the signed CLI artifact of run 42373449340 and found the CLI step answered
**"Mosquito."**, and the canary passed anyway because it only checked that the answer was non-empty. The
call was real and witnessed, but the answer was wrong and nothing checked it. Logged as QOS-0025
(Sage's fix in #9). "Witnessed" proves a call happened; it says nothing about whether the answer was right.

---

## 2026-11-07 · Sage/Codex · Clean main-based signed integration of #9 and #10 documentation

The owner asked Sage to handle the integration/signing fixes. The existing #9 was retargeted to main, exposing squash ancestry (73-file conflicted ancestry diff versus ten actual tree changes). Preserve #9 at 336dfee9 and #10 at 1a1ca6f6 as source history; do not rewrite another engineer's branch.

- Prepared codex/smoke-main-signed directly from main 90b40356c07492df4ee179bd39177b03cb219f75. All prior candidate source blobs were checked before documentary reconciliation; provider/verifier/test code is unchanged from 336dfee934299b2d050e7729eb4b3dfea1e882b4.
- Incorporated Claude's exact appended landing/correction ledger text, protocol update, and QOS-0026 signing issue alongside Sage's QOS-0025. Both historical ledger contributions remain intact; the original canary's wrong CLI answer stays recorded.
- GitHub's web editor produced a Verified first commit 2a39032287183d35cb07d00e26d170e9c9c767f6 directly on the clean branch. This uses existing account access and GitHub web signing; no local key, security rule, reviewer policy or credential was created/changed. Verify every new contribution commit before landing. Source signatures establish attribution, not independent containment acceptance.
- Clean-copy baseline: 203 offline tests passed with the historical archive explicitly supplied; package import resolved to the fresh source; new local hive genesis signature verified. Seven historical replay cases skip in ordinary CI. No new model calls. Final-head CI/review and live upload confirmation remain separate observations.
- Relayed Claude review was supplied by Johnny and posted with attribution on #9. It predates the retention follow-up; it is not self-authored independent acceptance or automatically a full review of this integration.

Agent: Sage (Codex)
Codex-Session: 01a1ab22-a4f2-7852-b510-5973fd1a4952

---

## 2026-11-07 · Claude · M1 valve + claims landed (#11); VerificationGate

- **#10 closed as superseded.** Sage's #9 integrated all of its documentation (verified on `main` before closing).
- **#11 landed** (a1294f1): Bresslau valve, egg-lifecycle projection, Page-Robinson worker claims with per-egg
  capabilities (closes QOS-0020). Before the owner merged it, Claude merged it locally with post-#9 `main` and ran
  the suite: 218 passed.
- **This PR: VerificationGate** (`gate/gate.py`). It runs deterministic checks first and trusts nothing from the
  worker: artifact present / digest / canonical envelope, egg signature, schema re-validation, ≥1 receipt under
  the delivering capability re-derived from raw bytes (fixtures refused in production), and **delivered output
  == the JSON in a verified receipt**. Outcomes are fenced by a `gate:<egg>` lease. PASS → atomic promotion →
  `egg.hatched`. FAIL → oophagy (quarantine + capability revocation + `egg.purged`). Quorum ≥ 2 → `egg.held`
  (fail closed until the M2 verifier). Evidence packs are stored in the blob store and referenced by digest.
- **QOS-0009 fixed:** promotion publishes the verified bytes with `os.link` (atomic, no-replace). Two-thread race: one winner.
- **CLI:** `queen eggs`, `queen gate review`.
- **Evidence:** 12 gate tests. Attack arms that must end in purge: tampered staging, invented output under a real
  receipt (the "Mosquito" pattern from Sage's finding, now caught structurally), unwitnessed output, schema bypass
  written straight to staging, fixture receipt in a production hive. Plus quorum hold, concurrent gates, and
  undelivered eggs. 230 offline tests pass; ruff, mypy --strict and actionlint are clean.
- New issues: QOS-0027 (exact-match strictness vs. post-processing), QOS-0028 (quorum eggs held until M2),
  QOS-0029 (no code-egg ADR-143 checks yet), QOS-0030 (O(N) receipt scan).

Agent: Claude (Opus 5.5) · Claude-Session: session_01H8L4suEA6LERLtdVM52b3A

---

## 2026-11-07 · Claude · #12 and #13 landed; QOS-0031 closed

- **#13 landed** (`e59ba67b`): the CLI canary call sends the same system prompt as pytest. The canary had been red on
  `main` because the 0.5B model answers "bee" with the instruction and "beeedom" without it, at T=0, every time.
- **Evidence:** branch run 42390202843 `ARCHIVED_SMOKE_PASS` (reply "bee", signed 5-event chain). `main` run 42407907623
  on `e59ba67b` is success. The red `main` runs 42380605862, 42386170198, 42386561400 and 42407888634 (the #12 merge)
  all failed at `Require expected CLI answer` with reply `beeedom`. The wrong answers stay recorded; none were relabeled.
- **#12 landed:** VerificationGate with QOS-0009 atomic promotion (see the entry above).
- **QOS-0031 logged and closed** in `docs/ISSUES.md`. Remaining open: QOS-0025 (Sage: a live pass and retention witness
  are still needed) and QOS-0026 (local CLI signing). The semantic oracle is still fragile on a 0.5B model. Claude's
  split (deterministic harness echo oracle vs. non-blocking semantic check) is still proposed, pending Sage.

Agent: Claude (Haiku 5.5) · Claude-Session: session_01H8L4suEA6LERLtdVM52b3A


---

## 2026-11-07 · Sage/Codex · QOS-0032 strict receipt/output JSON binding

The owner reports Claude temporarily unavailable, assigns Sage construction leadership, and confirms no known unpublished structured-output work. Continue from main 349cbfb31734e26135bc00eb97ff71d3135b593b; preserve prior branches/attribution. No review requirement, workflow authority or branch protection is changed.

- **Defect:** Python JSON equality confused boolean true/false with numbers 1/0, also nested; default parsing collapsed duplicate keys. Schema-valid delivery could differ from recorded model JSON and still hatch. Logged QOS-0032; QOS-0008 ownership moves to Sage for the next provider change.
- **Fix:** strict response parsing rejects duplicate keys (including nested/escaped duplicates) and nonfinite constants. Revalidate the parsed response against the egg schema, then compare JCS bytes with delivery. Overflow/noncanonical values and excessive JSON nesting fail closed; no output repair, transform or extra inference. All receipts still undergo raw-byte/signature re-derivation before matching. Existing numeric 1/1.0 equivalence remains explicit.
- **Evidence:** all 82 starting blobs matched pinned main. Baseline 237 passed, one live deselected; fresh test-hive signed genesis verified. Before the fix, ten new attack cases wrongly hatched; eight controls/rejections passed. Final suite: 256 passed, one live deselected (14 new attack cases, five valid controls). Ruff and strict mypy passed. Fixtures remain fixture-marked in signed receipts and run only in test hives. No real model requests were made. Final signed-head CI/review and merge are separately pending.
- **Next:** QOS-0008 structured output, bounded resume capsules, validated oviposition/coordinator, then an exactly scoped authorized M1 live exit test. Code-egg checks, hostile-worker OS isolation and heterogeneous quorum are not supplied by this correction. Quorum eggs remain held.
- **Dated corrections:** 42380605862 was a feature-branch manual dispatch and failed inside the combined CLI step, not the later separate answer step. Echo quality is not guaranteed by T=0. Offline replay of main run 42407907623's externally hashed artifact established a strict bee pass; failed-answer retention was witnessed in 42386170198. Preserve earlier ledger text as chronology. Current main push CI/canary metadata (42421568374/42421568372, attempt 1) is healthy; their raw outputs were not replayed here.
- **Limits:** self-review/CI are producer evidence; the cross-lineage review gap remains while Claude is unavailable. No independent containment acceptance is claimed. Frozen v65 evidence and real-agent A/B/C NO-GO remain unchanged; hourly scope remains read-only. No House/Hermes/Honcho/service/cron/security-setting changes or private artifact exports.

Agent: Sage (Codex)
Codex-Session: 01a1ab22-a4f2-7852-b510-5973fd1a4952


---

## 2026-11-07 · Sage/Codex · QOS-0008 structured JSON output candidate

Continue from Verified main ef74948f63282f915bbcb70fee9e4454c1606757 after #15's explicitly owner-excepted squash. #15-only exception and its missing cross-lineage review do not transfer to this candidate. Main CI 42425715242 and canary 42425715251 passed; downloaded artifact 13594894666 matched its external API digest and replayed offline as ARCHIVED_SMOKE_PASS. QOS-0032 status is reconciled to landed; earlier pending text remains chronology.

- **Contract:** immutable canonical JsonSchemaOutput, conservative closed/required object schema profile, bounded schema size/depth/property/enum counts; no references, unsupported keyword stripping, coercion or repair. Native schema settings for Anthropic Messages, OpenAI Chat Completions, Gemini generateContent and Ollama local chat. Other compatible presets default unsupported; known Ollama cloud routes refused. Actual vendor/model acceptance is not claimed.
- **Receipts:** normal text remains v1 with legacy decoders. Structured v2 binds exact raw request/response and schema blobs with versioned strict admission. HTTP-error, incomplete, refused, malformed and schema-invalid responses retain signed rejected evidence, then raise; no invented completion fields, retry or budget refund. Known credential echoes still prevent persistence. Transport failure without a response remains spent/error, not a fabricated receipt.
- **Replay and gate:** derive mode/schema from stored request bytes, schema/decoder version and response again, reject forged admission/schema/downgrade, and keep strict egg schema + canonical receipt/output binding. JSON format does not authorize tools. CLI adds --json-schema; successful admission exits 0, received rejection exits 4 with receipt reference.
- **Evidence:** copied source matched all 82 main-tree blobs. Fresh baseline 256 passed and signed test-hive chain verified. Candidate 306 passed, one live deselected; 50 new offline tests, ruff and strict mypy pass. All mocked HTTP/inference receipts are fixture-kind inside signed records and test hives. Tests cover native field literals, malformed/error custody, reopen, no retry/extra spend, production refusal, tampering, gate and CLI. Initial lint findings were corrected; no model request/credential access/live dispatch occurred.
- **Sources:** current primary Anthropic/OpenAI/Ollama docs and Google's official REST discovery schema; links, read/access limits and wire fields are in STRUCTURED_OUTPUT.md. Google guide/reference redirects were unavailable; discovery field existence is not live execution evidence.
- **Limits/next:** QOS-0008 stays partial overall: streaming/general tools and real structured compatibility remain unverified. Final signed-head CI/review are pending at preparation. Next is a bounded digest-bound resume capsule, followed by validated oviposition/coordinator and a specifically authorized M1 exit test. No host/process containment, quorum or independent acceptance claim. No frozen-v65, service, policy, cron, other-agent or private-export changes.

Agent: Sage (Codex)
Codex-Session: 01a1ab22-a4f2-7852-b510-5973fd1a4952

Publication observation, same session: the browser interface reports unavailable; documented reacquisition failed. Connected Contents API created commit 2d908fb85fe89a2fb0350ef53714a11b0fb7f0cb, verified=false/unsigned. Preserve this observation and prepare the full candidate as a draft for CI/review; do not claim signed publication or weaken main protections. Asked the owner to restore the existing browser tab; no credentials or signing configuration requested.


## 2026-11-07 — Sage: bounded Sol witness candidate (QOS-0033)

Owner requested the next bounded test after #16 landed. Prepared a separate one-use main-only workflow with exact revision/owner/consent checks, lifetime first-run and no-rerun admission, expiry, one fixed synthetic structured request to gpt-6.1-sol (1024 completion tokens, no tools/retries), signed receipt custody, no-key export and offline replay. SO-0001 and the generic live workflow are unchanged. USD 0.05 is proposed for explicit owner approval, not a provider billing guarantee. Existing environment protections are preserved; unavailable metadata fails closed. No model or live credential accessed during preparation. All new inference tests are fixture-marked inside signed test-hive receipts. An initial timeout-export missing-directory failure was found and fixed; retain the negative case. Current local baseline: 297 passed, 9 explicit skips (7 private archive cases and 2 credential-home environment limitations); fresh signed test-hive genesis verified. Final candidate evidence is recorded separately after checks. Merge/dispatch, account/secret access and live compatibility remain pending; no independent review or frozen-v65 acceptance is claimed.

Agent: Sage (Codex)
Codex-Session: 01a1ab22-a4f2-7852-b510-5973fd1a4952

Candidate readback: 26 new offline admission/evidence tests pass; full local suite 323 passed, 9 explicit skips. Ruff check/format and strict mypy pass (34 package files and both new scripts). No live call or dispatch. Cross-platform CI and owner merge/run decision still pending.

CI qualification finding (run 42432759896, Windows/Python 3.13 job 128585040430): existing test_claims lease test expired its 50 ms wall-clock lease during claim binding. All new Sol tests passed. Replaced that test's sleep with a controlled per-ledger lease/capability clock and explicit advance beyond expiry; production code/fencing is unchanged. The nine claim tests pass locally. This preserves the failed run and requires fresh candidate CI, rather than rerunning for a lucky pass.


## 2026-11-08 — Sage: refresh landed-state handoff before capsule work

Owner requests handoff/build-map refresh first, then resume-capsule implementation. Main bb99eac08caed14e1df6e7a15b3702ed8acc6b6c is the Verified signed #17 squash; CI 42433446919 (13 jobs) and keyless canary 42433446928 passed. #16's structured slice is landed, not a pending candidate; live structured compatibility and streaming/general tools remain open. The owner separately approved #17's ONE Sol attempt (1024 completion tokens, USD 0.05, no tools/retries), but reports the environment key is not yet configured. No live Sol result is observed; exact-SHA/expiry/first-run checks remain controlling. Later main revisions do not inherit that run approval.

Rewrote HANDOFF for a cold reader, reconciled BUILD_MAP status/claims and the engineering protocol's stale candidate sentence. Historical entries, including unsigned publication and failed Windows CI, are preserved. Capsule row is the next slice, not built yet; removed unmeasured O(1)/token-win language. All 90 starting public blobs matched pinned main. Offline baseline: 323 passed, 9 explicit skips (7 retained-archive dependencies; 2 credential-home environment limitations). Fresh signed test-hive genesis verified. No runtime/provider/security/schedule changes or model calls in this refresh.

Agent: Sage (Codex)
Codex-Session: 01a1ab22-a4f2-7852-b510-5973fd1a4952
