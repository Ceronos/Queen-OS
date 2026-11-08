# HANDOFF → next engineer on Queen-OS

Updated November 8, 2026 by Sage/Codex. Johnny assigns Sage construction leadership while Claude is unavailable. Preserve Claude's work and attribution; owner exceptions are PR-specific.

## Current main and post-merge finding

Main is **01e52d4dfb24bb1d2e9381e8849051ce3d4b7ef9**, Verified signed squash of #18, parent bb99eac08caed14e1df6e7a15b3702ed8acc6b6c. Tree a26cc13df291e05054ca73a2962922500319f61d exactly matches the qualified candidate. The owner explicitly authorized #18 only. PR run 42478326333 attempt 1 passed all 13 jobs against synthetic merge d756a6d9 (parents bb99eac + 2b1777f).

**Main CI 42478678377 failed:** ARM64/Python 3.13 job 128725617876 hit the existing claim binder's relative-TTL clock race. Capability issuance read a later clock than the caller's remaining-lease calculation, so signed capability expiry could exceed lease expiry. The new capsule correctly refused that claim; do not relax its check. The failure is retained, not rerun for a lucky pass. Other 12 jobs passed.

**QOS-0036 follow-up candidate:** Authority.issue accepts an optional host absolute upper deadline, clamps expiry at the issuance clock read, and refuses an elapsed deadline before signing/appending. Worker binding supplies the original lease deadline. No signed wire fields, default issuance behavior, lease lifetime, resume checks or budgets are weakened. A controlled +1 ms-per-read regression fails on main and passes with the fix. Expiry during binding leaves only the already committed lease grant: no claim or capability; retain that partial history, do not imply multi-event atomicity. Legacy overlong capabilities are not repaired or silently resumed.

Candidate local suite: **375 passed, 9 skipped** (7 absent historical archive checks; 2 local credential-home fixture limitations); 9 new deadline cases. Ruff check/format and strict mypy pass. Cross-platform CI and exact revision evidence belong in the follow-up PR. It has no merge authorization yet.

## Other landed work and live evidence

- #15/QOS-0032: strict canonical receipt/output equality and ambiguous/type-substitution refusal.
- #16: structured JSON slice of QOS-0008. Streaming/general tools remain unfinished; live structured compatibility is unverified.
- #17/QOS-0033: one-use Sol witness, plus QOS-0034 controlled-clock lease test.
- #18/QOS-0035: bounded source-verified resume context, same-worker live unspent claim restore, no automatic effects. See docs/RESUME_CAPSULE.md.
- Main keyless canary **42478678093 failed before inference**: the pinned Ollama runtime download returned HTTP 504 and an incomplete archive. There is no semantic/receipt result for this revision. Do not infer regression or success from unavailable infrastructure. No rerun was dispatched.

Owner-approved Sol witness is still **ONE** gpt-6.1-sol request, 1024 completion tokens, USD 0.05, no tools/retries, pinned to bb99eac. The owner reports OPENAI_API_KEY not configured. No Sol run observed. Expiry 2026-11-10 00:00 UTC; failures/cancellations consume the first-run slot. Main has moved: obtain a newly scoped owner revision decision before launch, never transfer that approval silently. Read BOUNDED_SOL_SMOKE.md and exact workflow. SO-0001 is unchanged.

## Construction order

1. Qualify QOS-0036, obtain the specific review/owner decision, then use the protected signed merge path. PR #18 approval does not cover this follow-up. Keep both failed main runs as evidence.
2. With claim binding corrected, proceed to oviposition/coordinator: validate untrusted goal-to-DAG proposals, graph/budget failures and host publication. Model text cannot mint capabilities.
3. Prepare the M1 exit test after those pieces fit, under a separate exact revision/provider/call/token/cost scope. The one-use Sol witness is not that experiment.

Use offline fixtures while live setup waits. Read CLAUDE.md, ENGINEERS.md, the latest LEDGER and BUILD_MAP; run baseline and fresh signed hive verification. Source signatures establish attribution; producer tests establish only their observed scope. Cross-lineage review is absent while Claude is unavailable.

## Boundaries

Capsule verification is linear within hard limits, not O(1) or a measured token-saving claim. Spent/missing-response attempts require explicit reconciliation; no automatic retry. Oviposition and general reconciliation remain separate. Enclaves are in-process policy, not hostile-process containment (QOS-0006); code-egg checks remain partial (QOS-0029), quorum eggs HELD until M2 (QOS-0028). No generated-code/shell runner or expanded model authority is introduced. The hourly cadence remains read-only and separate from manual construction.

Historical wrong answers and failed runs remain recorded. Keep transport/path integrity, schema validity and semantic correctness distinct. Frozen Astra v65 remains unchanged/NO-GO: independent containment acceptance and a verified fresh-session adapter are absent. Repository models, owner merge decisions and green CI do not change that boundary.

Agent: Sage (Codex)
Codex-Session: 01a1ab22-a4f2-7852-b510-5973fd1a4952
