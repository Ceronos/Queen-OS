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
| QOS-0003 | S2 | owner-decision | — | C | Single-owner repo vs `live-inference` environment `prevent_self_review`: the owner cannot approve his own dispatch. A second reviewer is needed or the rule must change. |
| QOS-0004 | S3 | open | — | C/S | Continuous real-inference evidence was removed from PR CI (PR #3). There is now no automatic signal that the provider path still works against a real model. |
| QOS-0005 | S3 | open | — | C/S | Ollama installer/runtime unpinned (`curl … \| sh`). It is a supply-chain surface in the live workflow. |
| QOS-0006 | S1 | open | — | C | Enclave policy is in-process plus permission bits only. It does not stop a hostile local process. OS containment (Landlock/Job Objects/sandbox-exec) is M3. |
| QOS-0007 | S2 | open | — | C | Windows: the private host key relies on the user-profile ACL. There's no explicit ACL and no DPAPI/TPM sealing. |
| QOS-0008 | S3 | open | — | C | Providers are text-only: no streaming, tool calls or structured output. Diploid strict-schema eggs need structured output (M1.5). |
| QOS-0009 | S2 | open | — | C | The `Enclaves.promote` exists-check then `os.replace` is a TOCTOU race. On Windows `os.replace` overwrites, so two promoters could race. It needs a fenced lease or an atomic no-replace link. |
| QOS-0010 | S2 | open | — | C | HLC wall time comes from the local clock with no drift bound. A node whose clock jumps far ahead pins every successor's L to that value. No max-skew guard exists (Pillar 1 assumed PTP). |
| QOS-0011 | S3 | open | — | C | The ARM64 Linux target (Thelio Astra / Ampere Altra) had no CI coverage. |
| QOS-0012 | S3 | **fixed** (this PR) | Claude | C | Absent hardware (TPM/PTP/NUMA) had no honest probe. Pillar 1's own probe reports a missing PTP device as a pass. |
| QOS-0013 | S4 | owner-decision | — | S | Sage's notes cite an existing "research NO-GO / real-agent NO-GO" decision that is not recorded in this repo. Its text and scope need to be recorded here. |
| QOS-0014 | S3 | open | — | C | `verify_receipt` re-derives fields from raw bytes, but nothing ties the stored request bytes to the egg/capability that authorized the call (that comes with capability tokens). |
| QOS-0015 | S2 | open | — | C | Model lineage is inferred from a name-prefix table. A renamed or fine-tuned model could be misattributed, which would weaken quorum decorrelation. It needs explicit per-provider lineage declarations plus an `unknown` refusal in quorum. |
| QOS-0016 | S3 | open | — | C | `LEDGER.md`/`HANDOFF.md` are edited by both engineers on stacked branches, which guarantees merge conflicts. Process fix in `docs/ENGINEERS.md`. |
| QOS-0017 | S4 | open | — | C | LICENSE is engineer-drafted, not counsel-reviewed. |

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
