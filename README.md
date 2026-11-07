# Queen-OS

**A stigmergic, verification-gated multi-agent harness for any model.**
Windows · macOS · Linux · Python ≥ 3.12

Agents in Queen-OS do not talk to each other. A Queen compiles goals into signed
**Task Eggs** and lays them on **the Comb**, an append-only, hash-chained, HLC-ordered
ledger. Workers claim eggs through fenced leases, and their output lands in `staging`.
Nothing reaches `committed` until the **VerificationGate** has witnessed evidence for it.
The operating rule is **"Witnessed, not declared."**

> V5 unifies the Queen-OS V1–V4 blueprints into one non-simulated harness.
> [`docs/BUILD_MAP.md`](docs/BUILD_MAP.md) lists every blueprint concept, sorted into what
> a harness can run, what needs specific hardware, what is still research, and what is
> outside any harness.

## Status

| Milestone | Scope | State |
|---|---|---|
| **M0** | AF-SER-V1 / RFC 8785, hash-chained ledger, HLC, fencing leases, blob store, enclaves, Ed25519 identity, CLI | **built, tested** |
| M1 | Task Eggs, Bresslau valve, provider adapters + InferenceReceipts, capability tokens, workers, VerificationGate, oophagy | next |
| M2–M5 | governance, quorum, pheromone fields, host providers, federation | see build map |

## Quick start

```bash
pip install -e ".[dev]"
queen init ./my-hive --node-id alpha
queen ledger verify ./my-hive
queen ledger tail ./my-hive
pytest
```

## Layout

```
src/queen_os/
  serial/   RFC 8785 JCS + AF-SER-V1 post-write fetch
  comb/     ledger (QueenStore), HLC, leases, blobs, enclaves
  crypto/   Ed25519 identities
  hive.py   one hive on disk
  cli.py    `queen`
docs/BUILD_MAP.md   V5 concept → tier → module map
LEDGER.md           build ledger, one entry per session
HANDOFF.md          state for the next engineer
```

## Lineage

Queen-OS uses [Hermes Agent](https://github.com/NousResearch/hermes-agent) (MIT,
Nous Research) as its reference baseline for the model, tool and skill edge. Any Hermes
code ported into this repo keeps its copyright notice in `NOTICE`.
