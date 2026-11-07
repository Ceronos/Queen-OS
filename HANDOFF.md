# HANDOFF → next engineer on Queen-OS

_Last updated: 2026-11-07, Sage/Codex CI-authorization contribution._

## Read first

`CLAUDE.md` → latest `LEDGER.md` entry → `docs/BUILD_MAP.md`. Work lands through PRs; this branch is stacked on the existing M1 provider work, not a replacement for it.

## Existing PRs and remaining provider work

- Existing PR #1 is M0 → main; PR #2 is M1 providers → M0. Preserve that merge order and retarget dependent PRs after their bases land. The CI safeguard is stacked on the provider branch.
- The upstream handoff reports the earlier 9-job OS/Python matrix green and an earlier Ollama CI run. Those are upstream reports, not containment acceptance by this contribution.
- Provider streaming, tool/function calls and structured output remain planned M1.5 work. Credential custody is documented in `docs/SECRETS.md`; the proprietary license and source attribution are preserved.

## Current scope and evidence

- M0 contains the signed ledger/HLC, fenced leases, blobs, enclave conventions and CLI. M1 provider adapters/receipts and credential handling are present on the provider branch. Worker execution, TaskEgg/capability integration and the full VerificationGate remain separate M1 work.
- Existing code baseline: 89 offline tests passed locally. This CI-gate contribution: 110 offline tests passed on Linux / Python 3.12.3; lint/format and package/script type checks passed. Cross-platform results are left to the PR CI matrix and must be checked before claiming them.
- Ordinary push/PR CI is offline. A distinct manually dispatched workflow is the only CI inference entry. Read `docs/LIVE_INFERENCE.md` before proposing any live run.
- Live workflow preflight requires an exact approved main commit, provider/model/token scope and an already configured `live-inference` environment with required reviewers and self-review prevention. No environment, reviewer, key or live-run authorization was created by this change. No live run was dispatched.
- The review URL/checker does not establish independent containment acceptance or a monetary grant. Actual prerequisites remain the reviewer's responsibility. Existing research NO-GO decisions remain in force.

## Next engineering work

1. Review/land the CI safeguard before the next contribution.
2. Add offline ledger/lease interruption and post-commit-readback recovery contracts against the existing primitives. Do not substitute a parallel store or label fixtures as live inference.
3. Continue M1: TaskEgg and actual capability checks, worker claims, evidence gate, projections/recovery, and then an explicitly scoped integrated run after prerequisites. The build map defines ownership and milestone boundaries.
4. Keep source-signing, producer tests, independent review and deployed containment as separate evidence classes. Directory permissions are not an OS sandbox.

## Preserved open work

- Operational process containment, aggregate budgets and real cancellation/cessation need separate implementation and evidence.
- Reviewer/environment setup and model budget decisions are not supplied by this branch.
- Ollama runtime/installer pinning remains unresolved for future authorized live CI.
- Fixtures are tagged inside signed inference records and refused in production hives. No automatic model fallback, hidden live test, credentials in Git or service/schedule changes.

## Source reading still pending

The upstream handoff records V4 Treatise, V4 Phase 6, Execution Stacks, Deployment, Robotics, Unison-Bio, Master Compilation, Pillar 1 Report, Pillar 4, AF-IMMUNE-V1, AF-SWARM-V1, AF-BREED-V1 and WK1–WK7 as unread by its author. Read only the sources relevant to the next milestone; this contribution does not claim that corpus review.
