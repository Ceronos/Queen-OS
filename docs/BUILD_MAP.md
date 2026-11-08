# Queen-OS V5 Build Map

**Status:** v0.3, 2026-11-08. Landed-state refresh through signed main bb99eac (#17); source read-coverage below remains historical, not a claim of newly read blueprints.
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
| Pillar 1 Technical Specification (2026-11-07) | `1cw1oEw6…` | full (supersedes the empty `1XGDDEnN…`) |
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
| QueenStore append-only hash-chained ledger from `GENESIS_ROOT_0000000000000000` (Thesis §4.3) | T1 | SQLite WAL, `BEGIN IMMEDIATE` serialized appends, SHA-256 chain, full-chain verifier; failed-COMMIT/automatic-rollback cleanup with primary-error preservation | `comb/ledger.py` | **M0 ✅** |
| HLC `(L, C, node_id)` causal ordering (Thesis §4.3) | T1 | HLC persisted in the ledger so it stays monotonic across restarts. L is the system clock; PTP is optional host infra (T2). | `comb/hlc.py` | **M0 ✅** |
| State = deterministic fold of the event ledger (Thesis §4.3) | T1 | Pure projection functions over events. Rebuildable at any time. | `comb/projection.py` | **M1 ✅** (#11, eggs) |
| Content-addressed blob store (REMEDY §1.2) | T1 | `blobs/ab/<sha256>` with tmp + fsync + atomic replace + read-back verify | `comb/blobs.py` | **M0 ✅** |
| Atomic leases + monotonic fencing tokens (V2 remedy table) | T1 | Lease table plus signed grant/renew/release events with post-commit event readback. Positive integer durations; fenced appends reject stale holders. | `comb/leases.py` | **M0 ✅** |
| 5-tier spatial enclaves `/workspace /staging /committed /quarantine /vault` (Thesis §4.2) | T1 | Per-hive directory tree with in-process policy. Committed files are made read-only, quarantine is a no-exec convention, and vault holds keys. | `comb/enclaves.py` | **M0 ✅** (paths + promote/quarantine) |
| 256 GB hugepage POSIX shm comb, 65,536 spinlock cells (Thesis §4.1) | T2 | `multiprocessing.shared_memory` hot cache (works on all 3 OSes), sized from config. The ledger stays the source of truth. The 256 GB figure is a deployment parameter, not a constant. | `comb/hotcache.py` | M3 |
| Hexagonal axial-coordinate comb grid (V2) | T1 | Cell addressing `(q, r)` as an index over task and domain space, used for locality in work stealing | `comb/hexgrid.py` | M2 |
| CvRDT LWW cells + vector clocks for WAN (REMEDY §3.4) | T1 | Join-semilattice cell merges. Property tests check commutativity, associativity and idempotence. | `federation/crdt.py` | M5 |
| Merkle Search Tree state healing (REMEDY §3.4) | T1 | MST over ledger keys, root-digest exchange | `federation/mst.py` | M5 |
| Bounded resume capsules instead of context stuffing (V2 table) | T1 | Canonical packet anchored to a verified signed head, bounded ancestor closure/effect refs and source readback. Same-worker live unspent claim restore only; spent/unknown effects block. See RESUME_CAPSULE.md for hard limits, stale-head refusal and omitted transitive outputs. Verification is linear; token savings unmeasured. | `comb/capsule.py`, `Worker.resume`, CLI | **Landed #18; QOS-0036 corrected in #19. Main CI13/canary passed at 9a40642.** |

### Plane 2 — Control Plane (Queen Core)

| Concept | Tier | V5 realization | Module | Milestone |
|---|---|---|---|---|
| Oviposition Engine: goal → Task DAG (Thesis §5.1) | T1 | Candidate deterministic proposal admission against host objective/limits, bounded DAG and valve profiles; atomic signed publication, stable replay/conflict and read-only recovery. Shared task/goal call and requested completion ceilings checked before spend. See GOAL_PLANNING.md. Strategic model producer/live goal quality remain separate. | `queen/oviposition.py`, `queen/budget.py`, CLI | **M1 candidate QOS-0037; 57 offline cases; platform CI/review pending** |
| TaskEgg 7-tuple ⟨ID, Ploidy, Input, Schema, Tools, Stimulus, Signature⟩ (Thesis §5.1) | T1 | Frozen dataclass, JCS-canonical, Ed25519-signed. `goal_id`/`parents` make a DAG that is acyclic by construction. Input ≤ 8,000 canonical bytes (≈2k tokens). JSON Schema 2020-12, strict object schema for diploid. | `queen/egg.py` | **M1 ✅** |
| Bresslau's Valve: risk G → diploid (T≤0.2, strict schema) / haploid (T≥0.9) (Thesis §5.3) | T1 | Risk scorer (rules first, model optional) → execution profile | `queen/valve.py` | **M1 ✅** (#11) |
| Dual-brain: fast subconscious + strategic model (Thesis §6.1) | T1 | **Routing** between a fast/local model and a strategic model. The specific nets (Mamba `nox_soul.pt`, Gemma 4 MoE) are config, not code. | `queen/brains.py` | M2 |
| Spermathecal Vault: SLERP/TIES LoRA merging on demand (Thesis §5.2) | T3 | Model *registry* is T1. Weight-space merging is an offline tool via a mergekit adapter, run as an experiment. Merged weights only become usable after the eval gate passes. | `vault/registry.py`, `experiments/merge/` | M4 |
| Supersedure / emergency requeening, sub-500 ms failover (V1 plane 5) | T1 | Queen is a lease holder. A standby takes over on lease expiry, and the fencing token prevents split-brain. Real failover latency is measured, not claimed. | `queen/succession.py` | M3 |
| Swarming fission via spectral graph bisection (Thesis §9) | T1 / T2 | Spectral bisection of the task DAG is T1 (numpy). Streaming half the fleet to another host is T2 (federation). | `queen/fission.py` | M5 |

### Plane 3 — Worker Fleet

| Concept | Tier | V5 realization | Module | Milestone |
|---|---|---|---|---|
| Page-Robinson stimulus-response claim + work stealing (Thesis §5.3) | T1 | Workers poll stimulus scores and claim through a fenced lease. Idle workers steal from neighbouring cells. QOS-0036 candidate applies the lease's absolute deadline during capability signing; no expiry/fence check is relaxed. | `workers/claim.py` | **Landed #11; absolute-deadline correction #19 / QOS-0036 verified on main matrix** |
| Age-Polyethic State Machine driven by context use τ (Thesis §5.3) | T1 | Role state machine (Nurse→Maintenance→Forager→Vigil) driven by measured context utilization. Triggers compaction. | `workers/apsm.py` | M2 |
| H2O KV compaction / RadixAttention pruning | T3 | Server-side inference internals. The harness-side analogue is context compaction plus prefix-cache-preserving prompt layout (copied from Hermes's "prompt cache is sacred" invariant). | `workers/context.py` | M2 |
| Process isolation of workers | T1 / T2 | Subprocess workers on every OS. Landlock/seccomp (Linux), Job Objects (Windows) and sandbox-exec (macOS) are T2 providers. | `host/sandbox_*.py` | M3 |
| Wasm-sandboxed foraging and Tier-3 replay (V1 plane 4) | T1 | `wasmtime` (wheels for all 3 OSes) for deterministic tool replay | `gate/replay.py` | M4 |

### Plane 4 — Verification Plane (Immune System)

| Concept | Tier | V5 realization | Module | Milestone |
|---|---|---|---|---|
| AF-SER-V1 canonicalization + 6-step post-write fetch (P2 §4) | T1 | Real RFC 8785 JCS (UTF-16 key order, ES6 number format). Non-NFC strings are **rejected** rather than silently normalized, so data is never mutated. Post-write fetch is applied to blobs, enclave promotion and ledger rows. | `serial/jcs.py`, `serial/afser.py` | **M0 ✅** |
| VerificationGate staging→committed (P2 §3) | T1 | Append-only gate state machine. Promotion only with a passing evidence pack. | `gate/gate.py` | **M1 ✅** (#12: deterministic checks, fenced hatch/purge/hold; QOS-0032 landed #15: strict schema-valid canonical JSON receipt binding, ambiguity rejection) |
| ADR-143 Evidence Packs (P2 §3.2) | T1 | Schema + collectors (exit code, runtime, digests, pytest, ruff, radon CC, mutmut). **Thresholds are per-profile config.** The 98.4% mutation / CC≤5 values ship as the `sovereign` profile, not the default, because a universal CC≤5 rule would reject most real code. | `gate/evidence.py` | **partial** (#12: JSON-output checks; code checks QOS-0029) |
| InferenceReceipts (REMEDY §1.1) | T1 | Emitted by every provider adapter and host-signed. Raw bytes are stored, every claim is re-derivable, and fixtures are refused in production. | `providers/receipt.py` | **M1.3 ✅** (v1 text plus #16 v2 structured success/rejection custody/replay; live structured compatibility unverified) |
| Portable structured JSON output (QOS-0008) | T1 | Immutable bounded schema profile, native wire modes, strict response admission and versioned replay; no repair/retry or tool authority. Live compatibility unverified. | `providers/structured.py`, `providers/base.py`, `providers/adapters.py`, `providers/receipt.py`, `cli.py` | **M1 structured slice landed #16** (offline fixture/CI evidence; live structured witness, streaming/tools remain open) |
| Tri-Sovereign heterogeneous 2-of-3 quorum (REMEDY §1.4) | T1 | Quorum across *distinct* provider lineages, enforced by lineage id. Invoked by Bresslau risk so cost scales with G. | `gate/quorum.py` | M2 |
| Atomic Oophagy → /quarantine + signed receipt (Thesis §7.3) | T1 | `os.replace` into quarantine, signed tombstone event, worker termination | `gate/oophagy.py` | **M1 ✅** (#12: quarantine + capability revocation + signed `egg.purged`) |
| Multi-channel alerts + disk DLQ (P2 §5.2) | T1 | Async dispatcher (webhook/Slack/Discord/PagerDuty/SMTP), JSONL DLQ, exponential backoff | `alerts/` | M3 |
| Two-Arm control tests (P2 §6) | T1 | Every security boundary gets a negative-control test that must fail closed | `tests/two_arm/` | ongoing |

### Plane 5 — Governance & Authority

| Concept | Tier | V5 realization | Module | Milestone |
|---|---|---|---|---|
| Sage System-2 dispositions ACT / PROPOSE / HOLD (P2 §2) | T1 | Deterministic policy engine (authority lineage, resource footprint, dependency risk), with optional model-based consequence review. Every disposition is a sealed ledger event. | `sage/` | M2 |
| Smallest Justified Action rule | T1 | Policy constraint: proposals carry a blast-radius estimate, and the smallest one is preferred | `sage/policy.py` | M2 |
| `BEGIN_MGC_PAYLOAD` sealed canonical envelopes | T1 | Envelope codec over JCS bytes | `serial/envelope.py` | M1 |
| Tripartite Authority, capability-token TaskContracts (REMEDY §1.5) | T1 | Ed25519-signed capability tokens (subject/scope/providers/models/tools/output cap/call budget/expiry). Issued, revoked and spent on the ledger. The budget is reserved atomically **before** the call (8-process overspend test). `Inference.run` requires one. Receipts bind `token_id` + `spend_seq`. | `authority/` | **M1 ✅** (tool *registry* dispatch: next) |
| Credential custody (Resource Custody branch, REMEDY §1.5) | T1 | env → OS keyring → owner-only `secrets.env` (refused inside a git worktree). Fingerprints only. Redaction, plus a repo credential scan in CI. | `secrets.py` | **M1.3 ✅** |
| Dufour Ed25519 origin signatures (Thesis §5) | T1 | Host and queen keys, event signing | `crypto/keys.py` | **M0 ✅** (keys, sign/verify) |
| AF-CHARTER 2-of-2 multisig with YubiKey (Thesis §1) | T2 | The multisig *protocol* is T1 (two Ed25519 keys). FIDO2/YubiKey key storage is a T2 key provider. | `authority/multisig.py`, `host/fido2.py` | M3 |
| TPM 2.0 PCR 0–14 attestation (Thesis §3.1) | T2 | Linux: raw PCR 0–14 from `/sys/class/tpm/tpm0/pcr-sha256` (no tool-stdout hashing). Windows/macOS report `UNAVAILABLE` (M3). | `host/probe.py` | **probe ✅**; sealing M3 |
| NUMA caste zones A–D, core pinning (Thesis §3.2) | T2 | `os.sched_setaffinity` (Linux), `SetProcessAffinityMask` (Windows). macOS has no affinity API, so it is a no-op that reports `UNAVAILABLE`. | `host/affinity.py` | M3 |
| BMC out-of-band audit, PTP ±10 ns | T2 / infra | Out of scope for the harness binary. Documented as deployment prerequisites for the Enclave profile. | docs | — |

#### Pillar 1 spec review (v0.2): corrections V5 adopts

| Pillar 1 claim | Defect | V5 rule |
|---|---|---|
| `verify_ptp_clock_drift()` returns `True` with *"Nominal clock lock assumed in test environment"* when `/sys/class/ptp/ptp0` is missing | **Breaks the spec's own Non-Simulation Contract**: an absent sensor is reported as a pass. | A missing PTP device reports `UNAVAILABLE`. The hive records clock discipline as `system` vs `ptp` in genesis. Nothing assumes a lock. |
| PCR digest = SHA-256 of `tpm2_pcrread` **stdout text** | The digest depends on the tool's output format, which differs between tpm2-tools versions and locales. A tools upgrade looks like a firmware attack. | Hash the raw PCR values (bank, index, bytes) in canonical JCS. |
| Ed25519 host key "derived inside the TPM" | Most deployed TPM 2.0 parts implement NIST P-256 (and RSA), not Ed25519. | Either a TPM-resident P-256 attestation key, or an Ed25519 key **sealed** to a PCR policy and unsealed only on matching PCRs. Both are T2 providers. |
| `seed_capsule.py` uses stdlib only | Sound. Keep it. | `host/probe.py` imports stdlib only, so it can run before dependencies are installed. |
| "Direct bare-metal Ring-0 execution" | A Python userspace harness never runs in Ring 0. | The harness runs in userspace. Kernel/firmware hardening is a deployment-profile document, not harness code. |
| BMC "subverted into sovereign system controllers" | Firmware ownership is outside a harness. | Read-only BMC/IPMI health probe (T2) at most. |
| cgroups v2 slices per caste, `CPUSchedulingPolicy=rr` | Real, but Linux + systemd only. | `deploy/systemd/` unit templates for the Enclave profile (T2). Workers report their zone. |

### Plane 6 — Model & Tool Edge (from Hermes)

| Concept | Tier | V5 realization | Source in Hermes | Milestone |
|---|---|---|---|---|
| Any-model provider adapters | T1 | Raw-HTTP codecs: Anthropic, OpenAI, Gemini, Ollama, and OpenAI-compatible (LM Studio, vLLM, llama.cpp, OpenRouter, Groq, DeepSeek, xAI, Mistral, Together, Fireworks, Cerebras, Nous). Lineage is keyed by model family. Streaming and tool calls come in M1.5. | `agent/*_adapter.py`, `providers/` | **M1.3 ✅** (text) |
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


CI admission for this provider work is separated into offline push/PR checks and a manually authorized live workflow; see `LIVE_INFERENCE.md`. The gate script has synthetic-metadata tests only and is not independent containment acceptance.

Offline interruption/reopen regression contracts now cover the existing ledger and leases; see `RECOVERY_CONTRACT.md`. The subsequent transaction/lease hardening extension adds failed-commit cleanup and controlled abrupt-writer-exit tests; see `TRANSACTION_LEASE_RECOVERY.md`. These changes do not implement M1 projection/capsule recovery or establish process containment.


The bounded live-smoke acceptance contribution adds an offline signed-artifact verifier and explicit fixed-word oracle (QOS-0025); see `SMOKE_ACCEPTANCE.md`. Its follow-up admits and retains structurally valid CLI evidence before the separate semantic gate; wrong answers still fail. It distinguishes witnessed transport from answer correctness and leaves containment/fresh-session research acceptance separate.

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

1. ~~Pillar 1 doc empty~~. Resolved: `1cw1oEw6…` (2026-11-07).
2. ~~License~~. Resolved: proprietary, source-visible (`LICENSE`).
3. ~~Provider keys~~. Resolved: keys stay out of the repo. Live tests read them from GitHub Actions
   encrypted secrets or the user's OS keyring. See `docs/SECRETS.md`.


Bounded Sol witness landed #17 (QOS-0033): `scripts/bounded_sol_gate.py`, `scripts/bounded_sol_smoke.py` and the manual-only workflow concretize a single authorized test of the existing structured-output/receipt rows. This is experiment admission/evidence, not a new harness runtime module or recurring Sol order. Owner approved one request at bb99eac, 1024 completion tokens and USD 0.05; live execution is unobserved and key setup is pending. Later revisions need explicitly matched authorization. SO-0001 remains unchanged; see BOUNDED_SOL_SMOKE.md.
