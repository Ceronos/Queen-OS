# HANDOFF → next engineer on Queen-OS

Updated November 8, 2026 by Sage/Codex. Johnny assigns Sage construction leadership while Claude is unavailable. No known unpublished QOS-0008 work was reported. Preserve Claude's work and attribution; branch from main and keep owner-controlled signed merges.

## Verified starting point

Main is `bb99eac08caed14e1df6e7a15b3702ed8acc6b6c`, Verified signed squash of #17, with tree `3a525290a625a195a13592043c25106a8c5299ec`. Main CI 42433446919 passed all 13 jobs and the keyless canary 42433446928 passed. No open PR was observed when this contribution began. These are dated producer/GitHub observations, not independent containment acceptance.

- #15 / QOS-0032 landed strict schema-valid canonical JSON receipt/output binding and ambiguity/type-substitution rejection. Its one-time review exception was scoped to #15.
- #16 landed the structured-JSON slice of QOS-0008: immutable portable schemas, four native wire modes, raw accepted/rejected custody, signed v2 receipts, replay and CLI --json-schema. Main CI 42429769412 and keyless canary 42429769335 passed. Streaming/general tools remain unfinished and live structured compatibility is unverified.
- #17 / QOS-0033 landed the one-use Sol witness; QOS-0034 replaced a runner-latency-dependent lease test with a controlled clock. Initial Windows failure 42432759896 is preserved; corrected-head CI 42433128022 passed all 13 jobs before the merge. No production fence was weakened.
- Johnny separately approved #16 and #17 after author qualification while cross-lineage review was unavailable. Those decisions are not blanket approval of later PRs or independent review.

## Live Sol witness: approved, not executed

The owner approved ONE gpt-6.1-sol request, 1024 completion tokens, USD 0.05 allowance, no tools or retries, at approved main `bb99eac08caed14e1df6e7a15b3702ed8acc6b6c`. The owner reports OPENAI_API_KEY is not yet configured. No Sol workflow dispatch or result has been observed. Account/model access and environment readiness remain unknown.

Read BOUNDED_SOL_SMOKE.md and the exact workflow before launch. The one-use slot includes failures/cancellations and cannot be rerun; expiry is 2026-11-10 00:00 UTC. Do not dispatch to test credential setup. If main moves, the workflow's exact-SHA check requires a newly scoped owner decision before using the new revision; do not carry approval forward silently. SO-0001 is unchanged. Connected tools lack dispatch and the browser interface was unavailable; an owner launch may be needed.

## Current construction order

1. The handoff and BUILD_MAP refresh is the first commit of codex/resume-capsule. Historical candidate text remains in the append-only LEDGER, not as current instructions here.
2. Qualify the M1 resume-capsule candidate (QOS-0035), then obtain review/owner merge decision. See docs/RESUME_CAPSULE.md. It anchors bounded context to a verified signed head, includes dependency/effect references, refuses stale/missing/tampered/oversize sources, and restores only the same worker's existing live unspent claim. No automatic inference/retry, fresh capability or gate acceptance. Local suite: 366 passed, 9 skipped (7 absent historical archive, 2 local credential-home fixtures); ruff/strict mypy passed. Platform CI/revision evidence belongs to the PR; no new merge approval has been given.
3. Build oviposition/coordinator: validate an untrusted goal-to-DAG proposal before signed publication, including graph and budget failures. Models cannot mint capabilities.
4. Prepare the M1 exit test only after those pieces fit, with a separate exact revision/provider/call/token/cost scope. The single Sol witness does not authorize that experiment.

Use offline fixtures while live setup waits. Before source changes, read CLAUDE.md, ENGINEERS.md, the latest LEDGER entry and BUILD_MAP, then run the offline baseline and a fresh signed hive verification. Record local/CI scope and actual tested revisions. New contributions remain candidates until reviewed/owner-decided and protected signed merges complete.

## Boundaries and preserved failures

Repository enclaves are in-process policy, not hostile-process containment (QOS-0006). Code-egg checks remain partial (QOS-0029); quorum-demanding eggs remain HELD until M2 (QOS-0028). No generated-code/shell runner or model-authorized tool capability is introduced. The separate hourly remains read-only; manual construction is a distinct lane.

Historical run 42373449340 answered Mosquito.: transport/path evidence did not establish the bee oracle. Later dated keyless artifacts passed their stated checks; do not relabel the earlier wrong answer. Keep path integrity, schema validity and semantic correctness distinct. Earlier unsigned feature commits and unavailable browser signing are publication history; #16/#17 landed through Verified protected squash commits without changing protections.

Frozen Astra v65 is unchanged and NO-GO for A/B/C comparisons: independent containment acceptance and a verified fresh-session adapter are absent. Repository models/adapters, owner merge decisions and CI do not change that boundary.

Agent: Sage (Codex)
Codex-Session: 01a1ab22-a4f2-7852-b510-5973fd1a4952
