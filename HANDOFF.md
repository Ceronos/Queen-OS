# HANDOFF → next engineer on Queen-OS

_Last updated: 2026-11-07 by Claude, newest PR in the stack (#5)._

## The stack (merge in order, retargeting each onto `main` as its base lands)
| PR | Branch | Author | Content |
|---|---|---|---|
| #1 | `claude/m0-substrate` | Claude | M0 substrate, license, build map |
| #2 | `claude/m1-providers` | Claude | providers, InferenceReceipts, credential custody |
| #3 | `codex/gate-live-inference-ci` | Sage | offline PR CI; reviewer-gated live-inference workflow |
| #4 | `codex/offline-recovery-contracts` | Sage | ledger/lease interruption + reopen contracts |
| #5 | `claude/m1-eggs` | Claude | issues ledger, engineer protocol, idempotent appends, host probe, ARM64 CI, capabilities, TaskEggs |

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

## Waiting on the owner
- QOS-0003: `prevent_self_review` with one human owner. Add a second reviewer, or have an engineer dispatch while you approve.
- QOS-0004: whether to restore a keyless local-model check on `main` pushes.
- QOS-0013: record the text of the "research / real-agent NO-GO" decision Sage references.
- Put the Anthropic key in **Settings → Environments → `live-inference` → secrets** as `ANTHROPIC_API_KEY`. Not in chat.
- Review and merge the stack #1 → #5.

## Commands
```
pip install -e ".[dev]"; pytest --ignore=tests/live          # 147 offline tests
queen init ./h --node-id dev && queen host probe --hive ./h && queen ledger verify ./h
env -u GH_TOKEN gh api repos/Ceronos/Queen-OS/...            # REST only from Claude sessions
```
