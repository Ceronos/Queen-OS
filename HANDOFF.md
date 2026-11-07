# HANDOFF → next engineer on Queen-OS

_Last updated: November 7, 2026 by Sage/Codex; clean signed main-based integration._

## Current contribution

`codex/smoke-main-signed` starts directly at main `90b40356c07492df4ee179bd39177b03cb219f75`. It combines the exact provider/verifier/test changes from #9 head `336dfee934299b2d050e7729eb4b3dfea1e882b4` with the overlapping documentation from #10 head `1a1ca6f66868916cb4cbb4465d33906ebdbb8a56`. Historical branches/PRs are preserved. This fixes the squash ancestry conflict without forcing either engineer's branch. New contribution commits use GitHub's signed web-editor path; verify their final signatures and CI before landing.

- QOS-0025 remains the canary answer/evidence issue. QOS-0026 is the separate signing issue. Local CLI signing is still unconfigured; no new key or security-policy change was made.
- Claude's original landing entry and correction, and Sage's smoke/retention entries, are retained in LEDGER.md. New work branches from main; short explicit dependencies are allowed by docs/ENGINEERS.md.
- Original #9 had 13 green checks against its former landing-branch base. Those are historical results, not a new main-based integration pass. Final-head CI must be bound to its actual tested commit and base/head.

## Smoke evidence and limits

Read docs/SMOKE_ACCEPTANCE.md. Historical run 42373449340 exported the wrong CLI answer `Mosquito.` despite a green job. Corrected run 42380605862 at `9a907655de0f249f5a4001770a6de88e4bc30ab8` returned `bee` in pytest but `beeedom` in the CLI. Producer signatures passed; the strict word gate exited 2. Artifact upload was then skipped. Do not claim a strict semantic smoke pass.

The retention fix admits the signed public CLI bundle, uploads it, then checks the unchanged `bee` oracle against the pinned ZIP digest. Invalid/private/incomplete bundles block upload; a wrong answer keeps the job red. No prompt, model, two-call count, 32/16 output-token caps, inference retry, live trigger, hosted-key policy or environment setting is changed here. Earlier pytest failure/cancellation/structural rejection/upload failure can still leave no CLI artifact; pytest's separate hive remains unexported.

Clean-copy baseline: 203 offline tests with the preserved historical archive, correct fresh-source import, and a verified new local hive genesis. Ordinary CI explicitly skips seven archive replay cases. No new model call was made for this integration. GitHub upload behavior at the final source still needs a live witness. Source signing and producer CI are not independent containment acceptance.

## Next work

1. Check final signatures, CI, exact diff and cross-engineer review before owner landing; originals remain as review history until superseded deliberately.
2. Record any later bounded canary result separately; never turn the preserved wrong answer into a pass or retry until lucky.
3. Continue M1 implementation: valve, worker claim with per-worker/per-egg capabilities and fenced writes, structured output, verification gate, projections/capsules and oviposition. See docs/BUILD_MAP.md and docs/ISSUES.md; no worker/model runtime is implemented by this handoff.
4. Frozen Astra v65 stays separate and unchanged. Its independent containment/fresh-session prerequisites still govern its A/B/C comparison; they do not prohibit ordinary repository engineering.

Read CLAUDE.md, docs/ENGINEERS.md, docs/ISSUES.md, the latest LEDGER.md entry and docs/BUILD_MAP.md. Existing live-inference documentation governs other run paths; documentary labels and historical owner statements do not expand the hourly cadence's read-only scope.
