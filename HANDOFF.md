# HANDOFF → next engineer on Queen-OS

_Last updated: 2026-11-07, end of Session 001._

## Where things stand
- **M0 (substrate primitives) is built and tested.** The hive on disk has 5 enclaves, a hash-chained
  HLC-ordered signed ledger, fencing leases, a content-addressed blob store, Ed25519 host identity,
  and the `queen` CLI. See `LEDGER.md` Session 001 for the evidence table.
- `docs/BUILD_MAP.md` v0.1 is the plan. Every blueprint concept has a tier (T1–T4), a module and a milestone.

## Read before touching code
`CLAUDE.md` (laws) → `docs/BUILD_MAP.md` → `src/queen_os/comb/ledger.py` (everything builds on it).

## Next: M1 "First living hive", in this order
1. `queen/egg.py`: TaskEgg 7-tuple, JCS-canonical, host-signed. Ledger kind `egg.laid`.
2. `authority/`: capability tokens (Ed25519, scoped to egg + tools + expiry). Tool dispatch checks them.
3. `providers/`: adapter ABC + OpenAI-compatible + Anthropic + Gemini. Every call emits a signed
   `InferenceReceipt` (REMEDY §1.1). A fixture provider sets `provider_kind="fixture"` and production hives reject it.
4. `queen/valve.py`: Bresslau risk G → diploid/haploid execution profile.
5. `workers/claim.py`: Page-Robinson claim via `Leases`, with every write fenced.
6. `gate/`: evidence pack schema + collectors, VerificationGate (staging→committed via `Enclaves.promote`),
   and `gate/oophagy.py` (quarantine + signed tombstone event).
7. `comb/projection.py` + `comb/capsule.py`: state = fold(ledger), O(1) resume capsule.
8. `queen/oviposition.py`: strategic model decomposes a goal into a DAG of eggs.
**M1 exit test:** a real model run end-to-end, with `queen ledger verify` green afterwards.

## Reference material
- Blueprint corpus: owner's Google Drive (search "Queen-OS"). IDs are in `docs/BUILD_MAP.md`.
  Not yet read: V4 Treatise, V4 Phase 6, Execution Stacks, Deployment docs, Robotics, Unison-Bio,
  and the 6.5 MB Master Compilation. Read the ones relevant to each milestone before building it.
- Hermes Agent: `git clone --depth 1 https://github.com/NousResearch/hermes-agent` (MIT). Relevant
  areas: `agent/*_adapter.py`, `model_tools.py`, `toolsets.py`, `tools/mcp_tool.py`, `hermes_state_fts.py`.

## Open questions waiting on the owner
Pillar 1 doc is empty · license · provider keys for M1 / 3-lineage quorum.
