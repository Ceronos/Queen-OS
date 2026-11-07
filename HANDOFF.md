# HANDOFF → next engineer on Queen-OS

_Last updated: 2026-11-07 by Claude (VerificationGate PR). The previous handoff (Sage, signed main-based
integration of #9/#10) is summarized under "Smoke evidence" and preserved in git history._

## State of `main`
- Landed: #8 (stack #1–#6: substrate, providers, receipts, authority, eggs, live gate, canary), #9 (Sage:
  bounded smoke acceptance + signed-artifact verifier, which integrated #10's docs), #11 (valve, projection, worker claims).
- This PR adds the **VerificationGate**. With it, the M1 loop is complete in code:
  **lay egg → claim (lease + per-egg capability) → witnessed inference → schema-valid delivery → gate →
  hatched (committed/) or purged (quarantine/, capability revoked)**, with the next eggs unblocked by their parents' hatch.
- `main` requires signed commits. Engineers use the signed web-editor path or a signed squash (QOS-0026).

## Read first
`CLAUDE.md` (laws) → `docs/ENGINEERS.md` → `docs/ISSUES.md` → latest `LEDGER.md` entries → `docs/BUILD_MAP.md`.

## Smoke evidence (Sage's lane; see `docs/SMOKE_ACCEPTANCE.md`)
- Run 42373449340 was green but its CLI answered `Mosquito.`. Run 42380605862 answered `bee` in pytest and
  `beeedom` in the CLI. The strict word gate exited 2. **No strict semantic smoke pass is claimed.** Never
  retry until lucky, and never relabel the preserved wrong answer as a pass.
- The retention fix uploads the signed CLI bundle first, then checks the `bee` oracle against the pinned ZIP digest.
- Claude's open suggestion to Sage: separate *harness* liveness (echo oracle, deterministic) from *semantic*
  quality (factual question, non-blocking), so a 0.5B model's mistakes don't read as harness breakage.
- Frozen Astra v65 is separate and unchanged. Its containment/fresh-session prerequisites govern its A/B/C study,
  not ordinary repository engineering.

## M1 remaining, in order
1. **Structured output** in providers (QOS-0008): JSON-schema mode per vendor (Anthropic tool-forced JSON,
   OpenAI `response_format: json_schema`, Gemini `responseSchema`, Ollama `format`). Diploid eggs need it
   to pass `output_matches_receipt` reliably.
2. **`comb/capsule.py`:** O(1) resume capsule (egg + parent artifacts by digest), so a worker reads state, not chat.
3. **`queen/oviposition.py`:** a strategic model decomposes a goal into a DAG of eggs (validated, signed).
4. **M1 exit test** (live, through `live-inference.yml` under SO-0001): real model decomposes → real workers
   hatch → gate promotes/purges → `queen ledger verify` green. Record the evidence bundle.

## Operator commands
```
pip install -e ".[dev]"; pytest --ignore=tests/live      # 230 offline (+7 archive-replay skips)
queen init ./h --node-id dev && queen host probe --hive ./h
queen eggs --hive ./h                                    # lifecycle fold
queen gate review <egg_id> --hive ./h                    # exit 0 = hatched, 3 = purged/held
queen ledger verify ./h
```

## Waiting on the owner
- First SO-0001 hosted dispatch, which also confirms the `live-inference` environment configuration.
