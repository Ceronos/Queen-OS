# HANDOFF → next engineer on Queen-OS

Updated November 8, 2026 by Sage/Codex. Johnny assigns Sage construction leadership while Claude is unavailable. Preserve Claude's work and attribution. Owner merge exceptions remain PR-specific.

## Verified main and retained history

Main is **9a40642eb1b6675936e455ce931a7e3ec325949c**, Verified signed #19 squash, tree 98165a2977a1f6f8bfe495af0e6bd0a9ff3cfbfd. Main CI 42480079372 passed all 13 checks, and automatic keyless canary 42480079373 passed. Read canary job 128729897305: retained-path verification and separate expect-word bee both pass. This is dated producer evidence, not general model competence or independent containment acceptance.

- #16: QOS-0008 structured JSON slice landed; streaming/general tools and broad live compatibility remain unfinished.
- #17: one-use Sol witness and QOS-0034 controlled-clock test landed.
- #18: QOS-0035 source-verified bounded capsule landed under its specific owner exception.
- #19: QOS-0036 absolute lease deadline correction landed under its separate owner exception. No capsule/fence/expiry check relaxed.
- Preserve main CI 42478678377 (01e52d4 ARM64 clock drift) and keyless canary 42478678093 (HTTP504 runtime download before inference). Later green does not relabel either failure.

## Current candidate: QOS-0037 goal-to-task admission/publication

Johnny asks to validate proposed task graphs and budgets before publication, and explore cheaper model testing while the Sol key is absent.

queen/oviposition.py validates inert UTF-8 proposals against a separate host objective and PlanBudget, derives existing valve profiles, rejects malformed/cyclic/oversize/external/M2-dependent work and atomically signs/appends every egg plus goal.planned. Stable goal ID gives exact canonical replay or conflict, and read_plan resolves uncertain postcommit returns without repeating writes.

queen/budget.py intersects later spending with admitted task calls/output/tools and goal call/completion-token ceilings in the existing writer transaction. Replaced capabilities cannot reset lifetime task allowance. Unknown effects retain their reservations. These units are requested completion ceilings, not input-token, USD, energy or wall-time accounting. No automatic provider, scheduler or tool dispatcher is introduced.

CLI: plan validate / publish / show. See docs/GOAL_PLANNING.md and examples/goal-plan.json. 57 new offline cases; local full suite **432 passed / 9 skipped** (7 absent historical archive checks; 2 local credential-home fixture restrictions). Ruff/format and strict mypy (37 source files) pass. Platform CI and exact revision evidence belong to this PR. No merge approval or cross-lineage review yet.

## Model testing: preserve scope and use evidence honestly

See docs/MODEL_TESTING.md for current primary-source options: fixture/replay reuse, existing local providers, constrained output, and conditional subscription API credits. Repository presets already include local servers; generic compatible presets do not automatically advertise native structured-output support. QOS-0038 is a qualification follow-up, not a live result or provider change.

Sol remains ONE gpt-6.1-sol request / 1024 total completion tokens / USD0.05 / no tools or retries. Key setup is owner-controlled; none was configured or read here and no Sol dispatch occurred. Original approval was pinned to bb99eac. Main moved, so bind a concrete current revision decision before launch; the fixed expiry remains 2026-11-10 00:00 UTC. Do not test key presence by consuming the first-run slot or silently extend expired admission. This does not extend SO-0001.

Local model inventory, host availability and account details stay in local work receipts, not public source. No weight download, model load or inference was performed in this contribution. No credential/session-token copying, service/startup changes or paid API request.

## Next work

1. Qualify/review QOS-0037 and obtain its own owner merge decision while Claude is unavailable; prior approvals only covered #15–#19 individually.
2. Establish the exact existing local model/server/version and a bounded synthetic witness, then retain/replay evidence. Keep local protocol compatibility, schema validity, graph/budget validity and semantic goal quality distinct.
3. Wire a strategic proposal producer through the existing witnessed-provider path only under a separate concrete call scope. The validator must still refuse bad proposals; model text never mints authority.
4. Prepare an M1 exit experiment after the pieces fit, with exact candidate/provider/model/calls/tokens/cost/time and independent-review limits. A single canned witness or fixture graph is not the M1 exit.

Read CLAUDE.md, ENGINEERS.md, latest LEDGER and BUILD_MAP before changes; baseline plus fresh signed hive verification. Contributions branch from main and land through protected signed squash merges.

Frozen Astra v65 remains untouched/NO-GO: independent containment acceptance and a verified fresh-session adapter are absent. In-process repository controls, model adapters, CI and owner merge decisions do not replace those gates. The separate hourly stays read-only and documentary; manual construction is a distinct lane.

Agent: Sage (Codex)
Codex-Session: 01a1ab22-a4f2-7852-b510-5973fd1a4952
