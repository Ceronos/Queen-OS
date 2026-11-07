# HANDOFF → next engineer on Queen-OS

_Last updated: 2026-11-07, Session 001 end._

## Where things stand
- **PR #1** (`claude/m0-substrate` → `main`): M0 substrate, proprietary LICENSE, build map v0.2. CI green on 3 OS × 3 Pythons.
- **PR #2** (`claude/m1-providers` → `claude/m0-substrate`): providers, InferenceReceipts, credential custody, live CI.
  Merge #1 first, then retarget #2 to `main`.
- `docs/BUILD_MAP.md` v0.2 is the plan (rows marked ✅ are built). `docs/SECRETS.md` covers key handling.

## Non-negotiables you inherit
Read `CLAUDE.md`. In short: witnessed not declared · the ledger is the only channel · authority comes only
from signed tokens · decorrelated verifiers · fail closed · cross-platform · tier honesty.
Plus: **no credential ever enters the repo.** Keys live in env / OS keyring / owner-only `secrets.env` / GitHub encrypted secrets.

## M1 remaining, in this order
1. `queen/egg.py`: TaskEgg 7-tuple, JCS-canonical, host-signed. Ledger kind `egg.laid`.
2. `authority/`: Ed25519 capability tokens (egg-scoped tools + expiry). Tool dispatch checks them.
3. ~~providers + receipts~~ ✅ (M1.3). Still to add: streaming, tool/function calls, and structured output
   (JSON-schema mode per vendor). These are needed for diploid strict-schema eggs.
4. `queen/valve.py`: Bresslau risk G → execution profile (temperature, schema strictness, quorum size).
5. `workers/claim.py`: Page-Robinson claim via `Leases`. Every write is fenced. Workers call `Inference.run`.
6. `gate/`: evidence packs, VerificationGate (`Enclaves.promote`), oophagy with a signed tombstone.
7. `comb/projection.py` + `comb/capsule.py`.
8. `queen/oviposition.py`: goal → DAG of eggs via a strategic model.
**M1 exit test:** real model end-to-end in a production hive, with `queen ledger verify` green.
In CI, Ollama is the always-on real model. Hosted APIs run when secrets exist.

## Useful commands
```
pip install -e ".[dev]"; pytest                      # unit (live excluded)
QUEEN_LIVE_TARGETS="ollama=qwen2.5:0.5b" pytest -m live -rs
queen init ./h --node-id dev && queen providers && queen infer ollama qwen2.5:0.5b "hi" --hive ./h
env -u GH_TOKEN gh api repos/Ceronos/Queen-OS/...   # GraphQL is blocked in Claude sessions; use REST
```

## Corpus not yet read
V4 Treatise, V4 Phase 6, Execution Stacks, Deployment docs, Robotics, Unison-Bio, the 6.5 MB Master
Compilation, Pillar 1 Report (`1ge6wMjn…`), Pillar 4 (`1NtEtxPo…`), AF-IMMUNE-V1, AF-SWARM-V1, AF-BREED-V1,
Sovereign Waking Protocol WK1–WK7. Read the ones relevant to each milestone before building it.

## Waiting on the owner
- GitHub repository secrets: `ANTHROPIC_API_KEY` (and optionally `OPENAI_API_KEY`, `GEMINI_API_KEY`).
- Review and merge PR #1, then PR #2.
