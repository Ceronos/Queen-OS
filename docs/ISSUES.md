# Queen-OS Known Issues Ledger

Every known defect, gap, risk and spec disagreement, from any engineer or from Red Team.
This is **separate from `LEDGER.md`**, which records what happened in each session. This file records what is wrong.

## Rules
- **Append-only IDs.** The next issue gets the next `QOS-####`. IDs are never reused or renumbered.
- **Never delete a row.** Close it by changing `Status` and naming the evidence (PR, test, CI run).
- **Claim before working.** Set `Owner` in the same PR that starts the fix, so two engineers don't collide.
- **Severity:** `S1` integrity/security/data loss · `S2` a wrong result or a broken contract · `S3` gap/hardening · `S4` docs/ops.
- **Status:** `open` · `claimed` · `fixed` (with evidence) · `wontfix` (with reason) · `owner-decision` (needs Ceronos).
- **Sources:** `C` = Claude, `S` = Sage, `RT` = Red Team, `O` = owner.

## Index

| ID | Sev | Status | Owner | Src | Summary |
|---|---|---|---|---|---|
| QOS-0001 | S1 | **fixed** (this PR) | Claude | S | Append can commit, then raise during readback. A naive retry duplicates the effect. No ledger-enforced idempotency. |
| QOS-0002 | S3 | **fixed** (this PR) | Claude | S | Credential-store tests fail when the OS temp directory has a git ancestor (the refusal is correct; the fixtures are wrong). |
| QOS-0003 | S2 | **fixed** (#5) | Claude | C | Single-owner repo vs `live-inference` environment `prevent_self_review`: the owner could not approve his own dispatch. **Owner decision:** standing order SO-0001 lets Claude/Sage dispatch within a scope enforced at the approved main commit (`governance/`). |
| QOS-0004 | S3 | **fixed** (#5) | Claude | C/S | Continuous real-inference evidence was removed from PR CI (PR #3). **Owner decision:** keyless local canary on push to main (`live-canary.yml`). Rationale for Sage in `docs/LIVE_CANARY.md`. |
| QOS-0005 | S3 | **partial** (#5) | Claude | C/S | Ollama installer/runtime unpinned (`curl … \| sh`). The runtime is now pinned to 0.40.15 and asserted. The installer script is still fetched unpinned, so it should be replaced with a checksummed release tarball. |
| QOS-0006 | S1 | open | — | C | Enclave policy is in-process plus permission bits only. It does not stop a hostile local process. OS containment (Landlock/Job Objects/sandbox-exec) is M3. |
| QOS-0007 | S2 | open | — | C | Windows: the private host key relies on the user-profile ACL. There's no explicit ACL and no DPAPI/TPM sealing. |
| QOS-0008 | S3 | **partial — structured-output candidate** | Sage | C | Native JSON-schema modes, strict portable request contract, v2 signed receipts/replay and CLI added in this candidate. Offline fixtures only; live structured compatibility remains unverified. Streaming and general tool execution remain open. See STRUCTURED_OUTPUT.md. |
| QOS-0009 | S2 | **fixed** (#12) | Claude | C | The `Enclaves.promote` exists-check then `os.replace` was a TOCTOU race, and on Windows `os.replace` overwrites. Now the verified bytes go to a temp file in `committed/` and are published with `os.link` (atomic, no-replace on POSIX and NTFS). Two-thread race test: exactly one winner, no overwrite. |
| QOS-0010 | S2 | open | — | C | HLC wall time comes from the local clock with no drift bound. A node whose clock jumps far ahead pins every successor's L to that value. No max-skew guard exists (Pillar 1 assumed PTP). |
| QOS-0011 | S3 | **fixed** (#5, run 42371711017+) | Claude | C | The ARM64 Linux target (Thelio Astra / Ampere Altra) had no CI coverage. `ubuntu-24.04-arm` × 3 Pythons is now green. |
| QOS-0012 | S3 | **fixed** (this PR) | Claude | C | Absent hardware (TPM/PTP/NUMA) had no honest probe. Pillar 1's own probe reports a missing PTP device as a pass. |
| QOS-0013 | S4 | **resolved** (owner) | — | S | Sage's notes cite a "research NO-GO / real-agent NO-GO" decision. **Owner (2026-11-07):** a precautionary artifact still being worked out, with Sage now focused on real-agent orientation. It is not a standing prohibition on this repo's work. |
| QOS-0014 | S3 | **fixed** (this PR) | Claude | C | `verify_receipt` re-derived fields from raw bytes, but nothing tied the call to the capability that authorized it. Receipts now carry `token_id` + `spend_seq`, which are verified against a prior `capability.spent` for the same provider/model. |
| QOS-0015 | S2 | open | — | C | Model lineage is inferred from a name-prefix table. A renamed or fine-tuned model could be misattributed, which would weaken quorum decorrelation. It needs explicit per-provider lineage declarations plus an `unknown` refusal in quorum. |
| QOS-0016 | S3 | open | — | C | `LEDGER.md`/`HANDOFF.md` are edited by both engineers on stacked branches, which guarantees merge conflicts. Process fix in `docs/ENGINEERS.md`. |
| QOS-0017 | S4 | open | — | C | LICENSE is engineer-drafted, not counsel-reviewed. |
| QOS-0018 | S4 | wontfix (design) | — | C | A capability spend is consumed even if the provider call then fails. This is deliberate: a non-refundable budget fails closed, and a call whose outcome is uncertain may have billed. |
| QOS-0019 | S2 | open | — | C | Token validity windows use the checking host's wall clock. With multi-node skew (QOS-0010), a token can appear valid early or late on another node. |
| QOS-0020 | S3 | **fixed** (#11) | Claude | C | Capability subjects allowed globs (`worker:*`). Worker claims now mint a capability whose subject is exactly one worker, scoped to one egg, expiring no later than the lease (`tests/test_claims.py`). Globs remain possible for operator-issued tokens. |
| QOS-0021 | S3 | open | — | C | The egg input bound is bytes/4 ≈ tokens, not a real tokenizer. It is uniform across models but approximate; CJK/code can exceed 2k real tokens. |
| QOS-0022 | S3 | open | — | C | `capability.spent` counting uses `json_extract` over all events (O(N) per check). It needs a generated, indexed `token_id` column before high-throughput hives. |
| QOS-0023 | S2 | **fixed** (#5) | Claude | C | `live-inference.yml` (#3) has been an **invalid workflow** since it landed: job-level `env` used `${{ runner.temp }}`, and the `runner` context is unavailable there. Every push produced a 0-job "failure", and no live run could ever have started. The fix sets `QUEEN_HOME` at runtime. `actionlint` now runs in CI so this can't recur silently. |
| QOS-0024 | S2 | **fixed** (#5) | Claude | C | `host probe` reported `clock_discipline=ptp` whenever a PHC device existed. On GitHub's Azure runner that was the **Hyper-V virtual** clock: the same "presence ≠ lock" defect Claude flagged in Pillar 1, now in Claude's own code. Caught by canary run 42373449340. Now: virtual PHCs (hyperv/kvm/vmware/virtio) are labelled, and the best possible discipline is `phc-unverified`. |
| QOS-0025 | S2 | **fix proposed** (Sage PR #9) | Sage | S | Nonempty wrong answers were accepted. Exact-word guard correctly rejected CLI `beeedom` in run 42380605862; upload was then skipped. Follow-up retains structurally admitted evidence before the separate word gate. A live pass and live retention witness are still required. |
| QOS-0026 | S3 | **partial** (signed web path; local CLI configuration absent) | Sage | C | `main` requires signed commits. Sage's Codex commits (#3, #4, #6) were **unsigned**, which blocked the stack from landing until it was re-landed as one signed commit (#8). A clean GitHub web-editor re-land provides verified signatures using existing account access; local CLI signing is still unconfigured. Verify each final commit, preserve attribution, and do not weaken branch rules. |
| QOS-0027 | S3 | open | — | C | The gate's `output_matches_receipt` requires the delivered output to *equal* the model's JSON. That's right for M1 (it blocks invented output), but workers that legitimately post-process will need a declared, replayable transform recorded in the evidence. |
| QOS-0028 | S3 | open (by design until M2) | — | C | Eggs with valve quorum ≥ 2 (G ≥ 0.8, e.g. `shell`) are always **HELD** by the gate, because the cross-lineage quorum verifier doesn't exist yet. Fail closed: they wait, they're never promoted. |
| QOS-0029 | S3 | open | — | C | Evidence packs cover JSON outputs only. ADR-143 code checks (exit code, tests, lint, CC, mutation) for code-producing eggs aren't collected yet. |
| QOS-0030 | S3 | open | — | C | The gate finds an egg's receipts by scanning all `inference.receipt` events (O(N)). The same indexing fix as QOS-0022 applies. |
| QOS-0031 | S2 | **fixed** (#13) | Claude | C | The live canary's pytest step sent a system prompt ("Return only the requested word.") and the `queen infer` CLI step did not. At temperature 0 the 0.5B model answers "bee" under the system prompt and "beeedom" without it, every time. The canary was red on every `main` push (runs 42380605862, 42386170198, 42386561400, and the #12 merge run 42407888634, all failing at `Require expected CLI answer`). Fix: the CLI call now sends the same system prompt. Evidence: branch run 42390202843 (`ARCHIVED_SMOKE_PASS`, reply "bee"); `main` run 42407907623 on `e59ba67b` (success). The strict word gate is unchanged. |
| QOS-0032 | S2 | **fixed** (#15) | Sage | S | Strict decoding, recorded-response schema validation and canonical-byte receipt/output binding landed as Verified ef74948. Owner granted review exception for #15 only; main CI 42425715242 and canary 42425715251 passed; downloaded artifact replay passed. |

| QOS-0039 | S3 | claimed (candidate) | Sage | S | Canary runtime HTTP504/truncated download is before model pull retries. Checksummed release acquisition, bounded transport-only retry and separate failure diagnostics proposed; real archive execution remains pending main canary. |

## Details

### QOS-0001 · Append committed, caller saw an exception
**Found by:** Sage (PR #4, `docs/RECOVERY_CONTRACT.md` case 2).
**Failure:** `Ledger.append` commits, then the post-write fetch raises (I/O error). The caller sees a
failure and retries, which produces two events for one operation. For an egg claim or an external tool effect, that is a double execution.
**Fix:** the ledger now has a unique `op_id` column. `append(..., op_id=…)` is idempotent: replaying the same
`op_id` with the same `(kind, actor, payload)` returns the original event, and replaying with *different*
content raises `IdempotencyConflict`. Tests: `tests/test_idempotency.py`.

### QOS-0002 · Credential tests and git-ancestor temp dirs
**Found by:** Sage (LEDGER, CI-gate entry). On hosts where `$TMPDIR` sits inside a repo, 2 tests fail.
**Fix:** credential tests create their own temp root, check that it has no `.git` ancestor, and skip with an
explicit reason if none can be found. The refusal itself is unchanged.

### QOS-0003 · Self-review prevention in a single-owner repo
GitHub's `prevent_self_review` stops the person who triggered a deployment from approving it. With
one human owner, a live run can only be approved if someone else dispatches it or reviews it. Options:
(a) add a second reviewer account, (b) let Sage or Claude dispatch while the owner approves, or (c) drop self-review prevention and accept that trade-off.

### QOS-0004 · Loss of continuous live evidence
PR #3's tradeoff is correct for hosted keys and cost. A keyless local-model check on `main` only (no
PRs) would bring back the "real inference still works" signal without touching secrets. This needs a decision between Sage, the owner and Claude.

### QOS-0012 · Honest hardware probe
**Fix:** `host/probe.py` (stdlib only, per Pillar 1's zero-dependency rule) plus `queen host probe`. Every sensor reports
`OK` / `UNAVAILABLE` / `ERROR` with the reason. It never assumes a pass. The report is a signed ledger event, which is
what Sage's Thelio Astra runs should produce as hardware evidence.

### QOS-0003 / QOS-0004 · Owner decisions (2026-11-07)
Owner's words: *"We can have Sage and you start runs under your own jurisdiction. Explicit via my orders, aka
Johnny."* and *"We need to ensure the real-model check is in place and that she is informed via documentation
from you about why."* Implemented as `governance/live_standing_order.json` (SO-0001) and `live-canary.yml`, and
explained to Sage in `docs/LIVE_CANARY.md`.


### QOS-0033 · Bounded GPT-6.1 Sol witness
**Owner:** Sage. **Status:** candidate; owner merge/run approval and live evidence pending. SO-0001 excludes Sol; do not broaden its recurring allowance for a single test. Proposed one-use workflow, one synthetic schema request, 1024 completion tokens, USD 0.05 allowance, exact main revision, no retries or tools. See BOUNDED_SOL_SMOKE.md. Account/key availability and provider behavior remain unknown. No workflow dispatch capability is exposed by the connected tools; signed-out CLI is a separate launch blocker.


### QOS-0034 · Lease expiry test depends on runner latency
**Owner:** Sage. **Status:** candidate test correction; new-head CI pending. Windows/Python 3.13 run 42432759896 expired a 50 ms lease before claim binding finished. The test now controls the per-ledger clock and explicitly advances beyond expiry; stale delivery and expired capability refusal remain asserted. No production lease, timeout or fence rule is weakened.


### 2026-11-08 landed-state correction — QOS-0008 / QOS-0033 / QOS-0034
Sage: structured JSON slice landed in #16; QOS-0008 remains partial for streaming/general tools and live compatibility. QOS-0033 witness code and QOS-0034 test-clock fix landed in #17 with green main CI/canary. The owner approved one Sol request at bb99eac; key setup/live execution remain pending. Earlier candidate text above is preparation history, not current merge status.


### QOS-0035 · Bounded verified resume context and existing-claim restore
**Owner:** Sage. **Status:** candidate, platform CI/review/owner merge decision pending. Added comb/capsule.py, deferred ledger snapshots, Worker.resume and capsule build/verify CLI. Packet context grants no authority; stale heads, altered source, missing evidence, resource overflow and unrecorded artifacts fail closed. Same-worker live unspent claim only; a spend with no receipt is uncertain, not retry permission. Complete bounded ancestor closure; only direct-parent outputs inline. See RESUME_CAPSULE.md. 43 new offline cases; local full suite 366 passed / 9 skipped. No live call or independent acceptance. Larger-ledger checkpoints, reconciliation broker, oviposition, performance/token measurement and M1 exit experiment remain separate.



### 2026-11-08 · QOS-0035 landed; QOS-0036 capability/lease deadline drift
**Owner:** Sage. **QOS-0035 status:** landed #18 at Verified signed 01e52d4, under the owner's #18-only review exception. PR matrix 42478326333 passed; main push run 42478678377 failed ARM64/Python 3.13 job 128725617876 in capsule reopen/resume, with the remaining 12 jobs passing.
**QOS-0036 status:** fix candidate; new CI/review/owner merge decision pending. Worker binding subtracted one clock reading from the lease deadline, then Authority.issue added a later reading to that relative TTL. The capability could outlive its lease by the elapsed interval. The capsule correctly rejects it. An advancing-clock test deterministically reproduced a +1 ms excess on unchanged main.

Authority.issue now optionally clamps expiry to the host's absolute not_after_ms at its own clock read; an elapsed deadline signs/appends nothing. Worker binding supplies its lease deadline. Default callers/wire shape remain unchanged, and resume/fence/expiry checks are not loosened. 9 added offline cases, including exact deadline, later-bound no extension, invalid types, and expiry before binding (the preexisting committed lease grant remains). Local full suite 375 passed / 9 skipped; ruff/strict mypy pass. Legacy overlong caps are not rewritten or silently resumed.

Separate infrastructure observation: main keyless canary 42478678093 / job 128725616179 failed the pinned Ollama installation with HTTP 504/incomplete archive, before inference. No semantic or receipt verdict exists for that revision; no rerun dispatched and no Sol slot consumed.


### 2026-11-08 landed-state correction — QOS-0035 / QOS-0036
Both landed under separate owner PR exceptions (#18 and #19). Main 9a40642 has successful CI 42480079372 (all 13 jobs) and keyless canary 42480079373 (job 128729897305, retained path plus explicit bee oracle pass). Earlier main clock-drift and pre-inference HTTP504 failures remain historical evidence; earlier candidate paragraphs are not the current state.

### QOS-0037 · Goal-to-task graph admission, publication and spend bounds
**Owner:** Sage. **Status:** candidate; platform CI/review/PR-specific owner merge decision pending. New oviposition module validates a bounded inert graph against a separate host objective/tool allowlist/call/completion budget and existing valve profiles. Rejects cycles, dangling/duplicate edges, invalid schemas/encodings, oversized input/canonical expansion and unavailable M2 quorum. Atomic signed eggs + goal.planned, stable dedup/conflict and read_plan recovery. Runtime shared spend checks intersect task calls/output/tools and goal ceilings across replacement capabilities; failures consume allowances. 57 new offline cases, full local 432 passed / 9 skips; ruff/strict mypy pass. See GOAL_PLANNING.md. Strategic generation, semantic goal acceptance, input-token/USD/energy accounting, automatic retries and M1 live exit remain separate.

### QOS-0038 · Qualify lower-cost local structured-model testing
**Owner:** Sage. **Status:** follow-up proposed, not implemented/qualified live. Existing local adapter presets and current LM Studio/llama.cpp/vLLM documentation offer candidate routes, but installed-version/schema/quantization/context evidence is needed. Current generic local presets do not advertise native structured-output support. MODEL_TESTING.md records fixture/replay reuse, local routes and conditional subscription API-credit eligibility, with a bounded witness/replay contract. No provider capability flag, model installation, paid call, workflow grant or standing order changed. The Sol key and exact fresh revision scope remain pending owner setup.


### QOS-0039 · Bounded verified canary runtime acquisition
**Owner:** Sage. **Status:** candidate; platform CI/review/PR-specific owner merge decision pending.
Run 42478678093 / job 128725616179 failed runtime installation with HTTP504/incomplete archive
before inference. Earlier wrong-answer failures remain QOS-0031; the strict oracle is unchanged.
This contribution replaces the streamed installer (QOS-0005 remainder) with a committed release
URL/size/SHA-256, three transport-only attempts, fresh partial files and mandatory verification
before private extraction. Separate phase summary and allowlisted infrastructure metadata retain
failure evidence without changing model-evidence admission. Forty new offline fault/contract cases;
no local runtime/weight download, model call or workflow dispatch. Actual extraction and new live
path remain unobserved until a future approved merge and its normal main canary.

### 2026-11-08 landed-state correction — QOS-0037
Goal admission/publication landed in #20 at Verified signed 9f294afcd46771772e35f419343161559cf12bfd
under its individual owner exception. Main CI 42484325300 passed all 13 jobs; keyless canary
42484325250 passed. Earlier candidate text records preparation, not current merge state. This is
not a strategic producer, general model competence or M1 exit experiment.
