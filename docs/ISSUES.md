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
| QOS-0008 | S3 | open | — | C | Providers are text-only: no streaming, tool calls or structured output. Diploid strict-schema eggs need structured output (M1.5). |
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
