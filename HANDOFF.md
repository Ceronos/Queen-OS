# HANDOFF → next engineer on Queen-OS

_Last updated: 2026-11-07 by Sage/Codex, bounded-smoke acceptance contribution on top of #5._

## The stack (merge in order, retargeting each onto `main` as its base lands)
| PR | Branch | Author | Content |
|---|---|---|---|
| #1 | `claude/m0-substrate` | Claude | M0 substrate, license, build map |
| #2 | `claude/m1-providers` | Claude | providers, InferenceReceipts, credential custody |
| #3 | `codex/gate-live-inference-ci` | Sage | offline PR CI; reviewer-gated live-inference workflow |
| #4 | `codex/offline-recovery-contracts` | Sage | ledger/lease interruption + reopen contracts |
| #6 | `codex/transaction-lease-recovery` | Sage | transaction cleanup, signed lease lifecycle (renew events), process-exit recovery tests |
| #5 | `claude/m1-eggs` | Claude | issues ledger, engineer protocol, idempotent appends, host probe, ARM64 CI, capabilities, TaskEggs, SO-0001, live canary, workflow fixes (rebased onto #6) |

## Bounded smoke milestone — latest contribution

The owner selected a bounded live harness smoke before the A/B/C study. Read `docs/SMOKE_ACCEPTANCE.md`. An actual earlier run proves a signed real-call path, but its exported CLI reply was `Mosquito.` to the comb question. QOS-0025 adds a fixed-word oracle and offline verification of the signed raw response; a corrected candidate needs its own live pass. The archived real-run fixture is retained locally and not published; replay tests require QUEEN_ARCHIVED_SMOKE and otherwise explicitly skip. It contains no vault/private key and is never presented as a new call. Local validation is 202 offline tests with no skips, clean lint/format and types; this PR needs its own CI and corrected live run. Frozen v65 remains separate; its research gates do not bar model-free repository work.

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
- **Keyless canary** (`live-canary.yml`) runs on every push to `main`. If it goes red, the real provider path is broken.
- **Engineer-dispatched runs:** `live-inference.yml` with `authorization_ref=standing-order:SO-0001`,
  `engineer=claude|sage`, within `governance/live_standing_order.json` scope (≤128 tokens, ≤20/day).
  The gate reads the order at the approved main SHA. The workflow is valid now (QOS-0023 fixed).

## Waiting on the owner
- Create the GitHub environment **`live-inference`** (Settings → Environments). For SO-0001 runs, add **no**
  required reviewers with self-review prevention. Add the secret `ANTHROPIC_API_KEY` there, not in chat.
- Review and merge the stack #1 → #2 → #3 → #4 → #6 → #5. The canary and live workflows only become
  dispatchable once they exist on `main`.

## Commands
```
pip install -e ".[dev]"; pytest --ignore=tests/live          # 186 offline tests
queen init ./h --node-id dev && queen host probe --hive ./h && queen ledger verify ./h
env -u GH_TOKEN gh api repos/Ceronos/Queen-OS/...            # REST only from Claude sessions
```
