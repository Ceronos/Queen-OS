# HANDOFF → next engineer on Queen-OS

_Last updated: 2026-11-07 by Claude, after the first stack landed on `main` (#8)._

## State of the repository
- `main` @ **90b4035** contains the whole first stack (#1–#6), landed via #8 as one signed squash. Its tree
  is identical to the reviewed head c802dc1. #1–#6 are closed with links. Their per-PR reviews and CI remain there.
- On `main`: **CI** (actionlint + Linux x64/ARM64, Windows, macOS × py3.12–3.14) and the **live canary**
  (keyless real model) are both green. The canary's first `main` run is 42379979225.
- New work branches from `main`. `main` requires signed commits (QOS-0025).

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
- Environment `live-inference` was created by the owner. Claude can't read its settings through the session
  proxy; the gate verifies them at dispatch time. The first SO-0001 dispatch confirms the configuration.

## Commands
```
pip install -e ".[dev]"; pytest --ignore=tests/live          # 186 offline tests
queen init ./h --node-id dev && queen host probe --hive ./h && queen ledger verify ./h
env -u GH_TOKEN gh api repos/Ceronos/Queen-OS/...            # REST only from Claude sessions
```
