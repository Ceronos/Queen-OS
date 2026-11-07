# Queen-OS V5 Build Map

**Status:** v0.1, 2026-11-07. Written at the start of the V5 build.
**Purpose:** list every concept in the Queen-OS V1–V4 blueprint corpus, sort each one by what a
software harness can actually run, and map it to a V5 module. V5 is the unified,
non-simulated harness. Anything in Tier 1 that is not built is a gap. Anything in Tier 3 or
Tier 4 that is ever presented as working is a Non-Simulation Contract violation.

## Sources read for v0.1

| Doc | Drive ID | Read |
|---|---|---|
| Master Thesis (AFRI-PUB-2026-QOS-THESIS) | `1tj6oFgX…` | full |
| Pillar 2 Deep-Dive (AF-SPEC-2026-QOS-P2) | `1jg_ppQX…` | full |
| V1 Spec + V2 Production Blueprint (PDF) | `1bB16guQ…` | five-plane topology + V1→V2 remedy table |
| AF-REMEDY-V1 (PDF) | `1NN-y4Ht…` | Ch.1 in full, §3.4 |
| Pillar 1 (Section 1 & Pillar 1) | `1XGDDEnN…` | **empty doc (1 KB) — flag to owner** |
| V4 Treatise, V4 Phase 6, Execution Stacks, Deployment docs, Robotics, Unison-Bio, 6.5 MB Master Compilation | — | **not yet read**. Planned for v0.2. |

Hermes Agent reference: `NousResearch/hermes-agent` @ `af5c2014` (MIT, Python ≥3.11, ~10.9k `.py` files).

---

## Tier definitions

| Tier | Meaning | Rule |
|---|---|---|
| **T1 — Harness-native** | Pure software. Buildable and testable on a laptop running Windows, macOS or Linux. | Must be built. CI must exercise it on all three OSes. |
| **T2 — Host-dependent** | Real, but only on certain hardware or OSes (TPM, YubiKey, Landlock, NUMA…). | An optional `host/` provider behind a capability probe. Absent hardware gives `UNAVAILABLE`, never a fake success. |
| **T3 — Research prototype** | A real research direction whose harness-side half can be built while the other half is open science. | We build the interface and an experiment harness, and record results as experiments, not features. |
| **T4 — Outside any harness** | Physical labs, quantum control electronics, wet biology. | Not in this repo. At most a documented adapter boundary (SAP) another system could implement. |

---

## Lessons from the V1 audit (AF-REMEDY-V1 Ch.1) — these are V5 design laws

1. **Fixtures must never look like execution.** V1 workers emitted hardcoded statuses and
   mock artifacts that had the same schemas as real calls. **V5 law:** every model call produces an
   `InferenceReceipt` (model id, prompt hash, completion hash, latency, raw bytes hash, host
   signature). Test doubles carry `provider_kind="fixture"` inside the signed receipt, and the gate
   rejects fixture receipts in any hive not opened in `test` mode.
2. **Docs are not ledgers.** Google Docs used as shared state lost revisions, interleaved
   concurrent appends and allowed duplicate task claims. **V5 law:** storage is SQLite WAL plus a
   content-addressed blob store; authority comes from leases with fencing tokens; hashing is
   RFC 8785. These are four separate tiers (causality / hash / authority / storage).
3. **Hardware unrealism.** V1 assumed several 70B models resident on 12–24 GB GPUs. **V5 law:** the
   default profile is *Workstation Edge*: one local control service, sequential or bounded-parallel
   dispatch, remote APIs for heavy inference. *Enterprise Enclave* is a deployment profile, not a
   requirement.
4. **Correlated Verifier Fallacy.** A model checking itself is collusion, not verification. **V5 law:**
   the quorum gate requires verifiers from **distinct provider lineages**, and deterministic checks
   (schema, AST, tests, replay) run before any LLM vote.
5. **Prompt-based authority.** **V5 law:** capability comes only from signed capability tokens issued
   by the host. Model text can never widen a grant.

---

## The map

### Plane 1 — Data & State Fabric ("The Comb")

| Concept (source) | Tier | V5 realization | Module | Milestone |
|---|---|---|---|---|
| QueenStore append-only hash-chained ledger from `GENESIS_ROOT_0000000000000000` (Thesis §4.3) | T1 | SQLite WAL, `BEGIN IMMEDIATE` serialized appends, SHA-256 chain, full-chain verifier | `comb/ledger.py` | **M0 ✅** |
| HLC `(L, C, node_id)` causal ordering (Thesis §4.3) | T1 | HLC persisted in the ledger so it stays monotonic across restarts. L is the system clock; PTP is optional host infra (T2). | `comb/hlc.py` | **M0 ✅** |
| State = deterministic fold of the event ledger (Thesis §4.3) | T1 | Pure projection functions over events. Rebuildable at any time. | `comb/projection.py` | M1 |
| Content-addressed blob store (REMEDY §1.2) | T1 | `blobs/ab/<sha256>` with tmp + fsync + atomic replace + read-back verify | `comb/blobs.py` | **M0 ✅** |
| Atomic leases + monotonic fencing tokens (V2 remedy table) | T1 | Lease table. Fenced appends reject stale holders. | `comb/leases.py` | **M0 ✅** |
| 5-tier spatial enclaves `/workspace /staging /committed /quarantine /vault` (Thesis §4.2) | T1 | Per-hive directory tree with in-process policy. Committed files are made read-only, quarantine is a no-exec convention, and vault holds keys. | `comb/enclaves.py` | **M0 ✅** (paths + promote/quarantine) |
| 256 GB hugepage POSIX shm comb, 65,536 spinlock cells (Thesis §4.1) | T2 | `multiprocessing.shared_memory` hot cache (works on all 3 OSes), sized from config. The ledger stays the source of truth. The 256 GB figure is a deployment parameter, not a constant. | `comb/hotcache.py` | M3 |
| Hexagonal axial-coordinate comb grid (V2) | T1 | Cell addressing `(q, r)` as an index over task and domain space, used for locality in work stealing | `comb/hexgrid.py` | M2 |
| CvRDT LWW cells + vector clocks for WAN (REMEDY §3.4) | T1 | Join-semilattice cell merges. Property tests check commutativity, associativity and idempotence. | `federation/crdt.py` | M5 |
| Merkle Search Tree state healing (REMEDY §3.4) | T1 | MST over ledger keys, root-digest exchange | `federation/mst.py` | M5 |
| O(1) resume capsules instead of context stuffing (V2 table) | T1 | Service-generated state-head capsule handed to an agent instead of chat history. **This is the real token win.** "Zero-token" is inaccurate: agents still read the capsule. | `comb/capsule.py` | M1 |

### Plane 2 — Control Plane (Queen Core)

| Concept | Tier | V5 realization | Module | Milestone |
|---|---|---|---|---|
| Oviposition Engine: goal → Task DAG (Thesis §5.1) | T1 | A strategic model decomposes the goal into a DAG, which is validated, signed and written to the ledger | `queen/oviposition.py` | M1 |
| TaskEgg 7-tuple ⟨ID, Ploidy, Input, Schema, Tools, Stimulus, Signature⟩ (Thesis §5.1) | T1 | Frozen dataclass, JCS-canonical, Ed25519-signed. Input bound is enforced by tokenizer estimate. | `queen/egg.py` | M1 |
| Bresslau's Valve: risk G → diploid (T≤0.2, strict schema) / haploid (T≥0.9) (Thesis §5.3) | T1 | Risk scorer (rules first, model optional) → execution profile | `queen/valve.py` | M1 |
| Dual-brain: fast subconscious + strategic model (Thesis §6.1) | T1 | **Routing** between a fast/local model and a strategic model. The specific nets (Mamba `nox_soul.pt`, Gemma 4 MoE) are config, not code. | `queen/brains.py` | M2 |
| Spermathecal Vault: SLERP/TIES LoRA merging on demand (Thesis §5.2) | T3 | Model *registry* is T1. Weight-space merging is an offline tool via a mergekit adapter, run as an experiment. Merged weights only become usable after the eval gate passes. | `vault/registry.py`, `experiments/merge/` | M4 |
| Supersedure / emergency requeening, sub-500 ms failover (V1 plane 5) | T1 | Queen is a lease holder. A standby takes over on lease expiry, and the fencing token prevents split-brain. Real failover latency is measured, not claimed. | `queen/succession.py` | M3 |
| Swarming fission via spectral graph bisection (Thesis §9) | T1 / T2 | Spectral bisection of the task DAG is T1 (numpy). Streaming half the fleet to another host is T2 (federation). | `queen/fission.py` | M5 |

### Plane 3 — Worker Fleet

| Concept | Tier | V5 realization | Module | Milestone |
|---|---|---|---|---|
| Page-Robinson stimulus-response claim + work stealing (Thesis §5.3) | T1 | Workers poll stimulus scores and claim through a fenced lease. Idle workers steal from neighbouring cells. | `workers/claim.py` | M1 |
| Age-Polyethic State Machine driven by context use τ (Thesis §5.3) | T1 | Role state machine (Nurse→Maintenance→Forager→Vigil) driven by measured context utilization. Triggers compaction. | `workers/apsm.py` | M2 |
| H2O KV compaction / RadixAttention pruning | T3 | Server-side inference internals. The harness-side analogue is context compaction plus prefix-cache-preserving prompt layout (copied from Hermes's "prompt cache is sacred" invariant). | `workers/context.py` | M2 |
| Process isolation of workers | T1 / T2 | Subprocess workers on every OS. Landlock/seccomp (Linux), Job Objects (Windows) and sandbox-exec (macOS) are T2 providers. | `host/sandbox_*.py` | M3 |
| Wasm-sandboxed foraging and Tier-3 replay (V1 plane 4) | T1 | `wasmtime` (wheels for all 3 OSes) for deterministic tool replay | `gate/replay.py` | M4 |

### Plane 4 — Verification Plane (Immune System)

| Concept | Tier | V5 realization | Module | Milestone |
|---|---|---|---|---|
| AF-SER-V1 canonicalization + 6-step post-write fetch (P2 §4) | T1 | Real RFC 8785 JCS (UTF-16 key order, ES6 number format). Non-NFC strings are **rejected** rather than silently normalized, so data is never mutated. Post-write fetch is applied to blobs, enclave promotion and ledger rows. | `serial/jcs.py`, `serial/afser.py` | **M0 ✅** |
| VerificationGate staging→committed (P2 §3) | T1 | Append-only gate state machine. Promotion only with a passing evidence pack. | `gate/gate.py` | M1 |
| ADR-143 Evidence Packs (P2 §3.2) | T1 | Schema + collectors (exit code, runtime, digests, pytest, ruff, radon CC, mutmut). **Thresholds are per-profile config.** The 98.4% mutation / CC≤5 values ship as the `sovereign` profile, not the default, because a universal CC≤5 rule would reject most real code. | `gate/evidence.py` | M1 |
| InferenceReceipts (REMEDY §1.1) | T1 | Emitted by every provider adapter and host-signed | `providers/receipt.py` | M1 |
| Tri-Sovereign heterogeneous 2-of-3 quorum (REMEDY §1.4) | T1 | Quorum across *distinct* provider lineages, enforced by lineage id. Invoked by Bresslau risk so cost scales with G. | `gate/quorum.py` | M2 |
| Atomic Oophagy → /quarantine + signed receipt (Thesis §7.3) | T1 | `os.replace` into quarantine, signed tombstone event, worker termination | `gate/oophagy.py` | M1 |
| Multi-channel alerts + disk DLQ (P2 §5.2) | T1 | Async dispatcher (webhook/Slack/Discord/PagerDuty/SMTP), JSONL DLQ, exponential backoff | `alerts/` | M3 |
| Two-Arm control tests (P2 §6) | T1 | Every security boundary gets a negative-control test that must fail closed | `tests/two_arm/` | ongoing |

### Plane 5 — Governance & Authority

| Concept | Tier | V5 realization | Module | Milestone |
|---|---|---|---|---|
| Sage System-2 dispositions ACT / PROPOSE / HOLD (P2 §2) | T1 | Deterministic policy engine (authority lineage, resource footprint, dependency risk), with optional model-based consequence review. Every disposition is a sealed ledger event. | `sage/` | M2 |
| Smallest Justified Action rule | T1 | Policy constraint: proposals carry a blast-radius estimate, and the smallest one is preferred | `sage/policy.py` | M2 |
| `BEGIN_MGC_PAYLOAD` sealed canonical envelopes | T1 | Envelope codec over JCS bytes | `serial/envelope.py` | M1 |
| Tripartite Authority, capability-token TaskContracts (REMEDY §1.5) | T1 | Ed25519-signed capability tokens. Tool dispatch checks the grant. Model text is never consulted. | `authority/` | M1 |
| Dufour Ed25519 origin signatures (Thesis §5) | T1 | Host and queen keys, event signing | `crypto/keys.py` | **M0 ✅** (keys, sign/verify) |
| AF-CHARTER 2-of-2 multisig with YubiKey (Thesis §1) | T2 | The multisig *protocol* is T1 (two Ed25519 keys). FIDO2/YubiKey key storage is a T2 key provider. | `authority/multisig.py`, `host/fido2.py` | M3 |
| TPM 2.0 PCR 0–14 attestation (Thesis §3.1) | T2 | Linux `tpm2_pcrread`, Windows `Get-PcrValue`/TBS. macOS has no TPM (Secure Enclave only) and reports `UNAVAILABLE`. | `host/tpm.py` | M3 |
| NUMA caste zones A–D, core pinning (Thesis §3.2) | T2 | `os.sched_setaffinity` (Linux), `SetProcessAffinityMask` (Windows). macOS has no affinity API, so it is a no-op that reports `UNAVAILABLE`. | `host/affinity.py` | M3 |
| BMC out-of-band audit, PTP ±10 ns | T2 / infra | Out of scope for the harness binary. Documented as deployment prerequisites for the Enclave profile. | docs | — |

### Plane 6 — Model & Tool Edge (from Hermes)

| Concept | Tier | V5 realization | Source in Hermes | Milestone |
|---|---|---|---|---|
| Any-model provider adapters | T1 | OpenAI-compatible (covers OpenRouter/vLLM/Ollama/llama.cpp), Anthropic, Gemini, behind one adapter ABC | `agent/*_adapter.py`, `providers/` | M1 |
| Tool registry + toolsets | T1 | Tools bound to capability tokens | `model_tools.py`, `toolsets.py` | M1 |
| MCP client (Adaptive Interface Discovery) | T1 | MCP tools with AST/schema drift checks (`verify_schema_drift`) | `tools/mcp_tool.py` | M2 |
| Skills (procedural memory) | T1 | Skills are ledger-tracked artifacts. A skill only becomes `committed` after passing the gate. | `skills/` | M2 |
| Session memory + FTS search | T1 | SQLite FTS5 over ledger projections | `hermes_state_fts.py` | M2 |
| Messaging gateway (Telegram/Discord/Slack…) | T1 | Plugin, not core | `gateway/` | M4 |
| Cron / scheduled eggs | T1 | Scheduled oviposition | `cron/` | M3 |

### Research & frontier (stigmergic alignment and beyond)

| Concept | Tier | What V5 builds | What stays open science |
|---|---|---|---|
| 6-channel pheromone fields QMP/QRP/Tergal/Dufour/Tarsal/Koschevnikov (Thesis §5) | **T1 core + T3 research** | Typed, decaying, signed signal streams on the comb. Tarsal is dedup trails, Tergal is a token-bucket spawn limiter, Koschevnikov is heartbeat/pain, Dufour is signatures, QMP carries alignment vectors (embeddings), and QRP is shared prefix/KV reuse. | Whether pheromone gradients produce better task allocation than a scheduler. **This is measurable: we run it as an A/B experiment.** |
| Stigmergic alignment (QMP v_align) | T3 | Alignment vectors as embeddings on the comb. Drift measured as cosine distance per worker output. Gate hooks on drift thresholds. | Whether embedding-space alignment pressure improves correctness. Experiment harness in `experiments/stigmergic_alignment/`. |
| Morphogenetic Substrate Engine (stem-cell core reallocation) | T3 | Role reallocation of *workers* driven by the pain index (T1). Core-level reallocation is T2. | Benefit vs. static pools. |
| Recursive Digital Gestation / Self-Entelechy (Thesis §8.3) | T1 / T3 | "Colony fork": seed invariants + config + skill lineage, packaged as a signed SoulCapsule and unfolded into a new hive under 2-of-2 multisig. Fully buildable. | Whether forked colonies improve. Measured by evals. |
| Landauer energetic check (Thesis §8.3) | T1 (reframed) | **Honest note:** kT·ln2 ≈ 2.85e-21 J per bit operation is about 10⁹× below real hardware energy, so as written the check never binds. V5 enforces a real **energy/token/$ budget ledger**. The Landauer bound is logged as the theoretical floor. | — |
| Autonomous Economic Subsystem | T1 (budget) / T4 (treasury) | Spend budgets per hive/egg, metered from receipts | "L2 honey treasuries": out of scope. |
| Tokenless Byte Latent Transformer | T4 (model-level) | Nothing. This is a model architecture. Adapters accept it if someone serves it. | — |
| Substrate Adapter Protocol `perceive()` / `cognate()` | T1 interface | The SAP ABC is the boundary where any external substrate plugs in | Implementations beyond software |
| Transmon QPU control, 35 ns CZ pulses, Tesseract QEC decoding (Thesis §8.2) | **T4** | SAP boundary only | Requires control electronics and a QPU vendor stack |
| Protocell synthesis, CRISPR, 5-mC methylation proof-of-life (Thesis §8.1) | **T4** | Nothing in this repo | Wet lab |
| Humanoid robotics via ROS2 (Thesis §8.1) | T2 plugin | Possible later ROS2 bridge plugin. Not core. | — |
| SCADA energy homeostasis, WireGuard planet mesh | T2 / infra | Federation transport is pluggable. WireGuard is deployment infra. | — |

---

## Milestones (top-down from the software core)

- **M0 — Substrate primitives (this session):** JCS/AF-SER-V1, hash-chained ledger with HLC, leases
  with fencing, blob store, enclaves, Ed25519 keys, CLI `queen init|ledger verify|ledger tail`, a
  3-OS CI matrix.
- **M1 — First living hive:** TaskEgg, Bresslau valve, oviposition, provider adapters with
  InferenceReceipts, capability tokens, worker claim loop, VerificationGate + evidence packs, oophagy,
  resume capsules, projections. **Exit test:** a real model decomposes a goal, real workers execute
  it, and the gate promotes or quarantines the results, all from a ledger that `verify` passes.
- **M2 — Cognition & governance:** Sage dispositions, heterogeneous quorum, AP-SM, dual-brain
  routing, MCP, skills, memory/FTS, hexgrid locality, pheromone fields v1.
- **M3 — Resilience & host:** succession/failover, hot cache, sandboxes, TPM/affinity/FIDO2 providers,
  alerts + DLQ, cron.
- **M4 — Edge & research:** gateway plugins, Wasm replay, model registry + merge experiments,
  stigmergic alignment experiments.
- **M5 — Federation:** CRDT cells, MST healing, fission, colony fork.

## Open questions for the owner

1. The Pillar 1 doc (`1XGDDEnN…`) is empty. Is there another copy?
2. A license is needed before the repo takes outside contributions (no license = all rights reserved).
   Hermes is MIT, so any code we port carries its notice in `NOTICE`.
3. Which provider keys exist for the M1 exit test and the 2-of-3 quorum (needs ≥3 distinct lineages,
   e.g. OpenAI, Google, Anthropic, or one local model)?
