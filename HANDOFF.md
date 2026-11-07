# HANDOFF → next engineer on Queen-OS

_Last updated: 2026-11-07 by Sage/Codex, failed-smoke evidence retention follow-up in PR #9._

## Observed repository state

The original stack has landed separately on main (observed `90b40356c07492df4ee179bd39177b03cb219f75`). PR #9 remains on `codex/bounded-astra-smoke`, based on `claude/v5-landing` at `2f0d338b997f63c1c9336548616e199dc664bee5`. PR #10 is a separate Claude documentation/protocol contribution; do not overwrite it or describe this follow-up as merged. Recheck remote heads and review before any integration.

## Bounded smoke milestone — latest contribution

The owner selected a bounded live harness smoke before the A/B/C study. Read `docs/SMOKE_ACCEPTANCE.md`. Historical CLI output was `Mosquito.` despite a green job. The explicit oracle at `9a907655de0f249f5a4001770a6de88e4bc30ab8` then ran in canary **42380605862, attempt 1**: pytest returned `bee`; CLI returned `beeedom`. Producer signatures passed; the word gate correctly exited 2. Upload was skipped, so fresh archive readback was unavailable. Do not claim a strict smoke pass.

This follow-up moves CLI evidence admission before upload and the answer gate after upload, binding both checks to one digest. Invalid/private/incomplete bundles still block export. Wrong answers retain admitted evidence and keep the job failed. No prompt, model-call count, token limit, live trigger, credential policy or oracle is changed. Offline validation: **203 tests passed**, plus Ruff/format and package/verifier mypy. Actual post-inference shell commands also passed an offline wrong-answer/private-file rehearsal with local retention. Replay uses the historical archive explicitly; seven archive-dependent cases skip when it is unavailable. It is not published or relabeled as new inference. GitHub upload behavior remains to be witnessed at the new revision. Frozen v65 stays untouched and requires its separate independent containment/fresh-session acceptance.

## Read first
`CLAUDE.md` (laws) → `docs/ENGINEERS.md` (how two engineers share this repo) → `docs/ISSUES.md`
(what is known to be wrong) → last `LEDGER.md` entries → `docs/BUILD_MAP.md`.

## State of M1
Done: providers + receipts · credential custody · capability tokens (budget reserved atomically, required by
`Inference.run`) · TaskEggs (signed 7-tuple, DAG by construction) · idempotent ledger ops.

Next, in order:
1. **`queen/valve.py`, Bresslau:** risk G → profile {temperature, schema strictness, quorum size, token budget}.
2. **`workers/claim.py`, Page-Robinson:** claim = lease(`egg:<id>`) + a **per-worker, per-egg** capability whose
   expiry is ≤ the lease (QOS-0020). Every write is fenced and carries an `op_id` (QOS-0001 contract).
   On restart, reconcile from stored evidence before any retry (Sage's `RECOVERY_CONTRACT.md`).
3. **Structured output** in providers (QOS-0008), needed to satisfy diploid schemas.
4. **`gate/`:** evidence pack → `jsonschema` validation of the output → `Enclaves.promote` or oophagy (signed tombstone).
   Fix QOS-0009 (promote TOCTOU) here with a fenced promotion lease.
5. `comb/projection.py` + `capsule.py`, then `queen/oviposition.py`.
**M1 exit test:** a real model decomposes a goal, real workers hatch the eggs, the gate promotes or quarantines,
and `queen ledger verify` is green. Live runs go only through `live-inference.yml` (see `docs/LIVE_INFERENCE.md`).

## Sage's lane (don't duplicate)
CI admission and live-run authorization, recovery/interruption contracts, Thelio Astra hardware runs
(`queen host probe --hive …` is the evidence format, see `docs/ENGINEERS.md`), containment evidence.

## Live inference (owner order SO-0001)
- **Keyless canary** (`live-canary.yml`) runs on every push to `main`. Inspect the failing step: provider/receipt failure, semantic mismatch and artifact upload failure are distinct outcomes.
- **Engineer-dispatched runs:** `live-inference.yml` with `authorization_ref=standing-order:SO-0001`,
  `engineer=claude|sage`, within `governance/live_standing_order.json` scope (≤128 tokens, ≤20/day).
  The gate reads the order at the approved main SHA. The workflow is valid now (QOS-0023 fixed).

## Remaining acceptance work
- Review PR #9 against its current head/base and this revision's CI. Merging remains separate.
- After offline checks pass, a separately authorized run at the new exact head can witness evidence upload and the subsequent strict answer result. No model retry is part of this follow-up.
- No hosted key, environment or reviewer setup is needed for this keyless retention fix. Existing live-inference documentation governs other paths; this change does not edit those settings.

## Commands
```
pip install -e ".[dev]"; pytest --ignore=tests/live          # 186 offline tests
queen init ./h --node-id dev && queen host probe --hive ./h && queen ledger verify ./h
env -u GH_TOKEN gh api repos/Ceronos/Queen-OS/...            # REST only from Claude sessions
```
