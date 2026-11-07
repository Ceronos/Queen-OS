# Queen-OS Build Ledger

Append-only. One entry per working session. Newest at the bottom.

---

## 2026-11-07 · Session 001 · M0 substrate primitives

**Engineer:** Claude Opus 5.5 (Claude Code session `session_01H8L4suEA6LERLtdVM52b3A`)
**Owner:** Ceronos Aethrion

### Decisions (owner-approved)
- Core language: **Python ≥ 3.12**, matching the Hermes Agent baseline. Targets Windows, macOS and Linux.
- Approach: write a **build map** of the V1–V4 corpus first, then build top-down from the software core.
- Canon: the Master Thesis + Pillar docs are the latest engineering read. V1/V2 and AF-REMEDY-V1 are
  consulted for components and failure lessons. V5 = curated, non-simulated unification.

### Decisions (engineering, open to Red Team challenge)
- JCS rejects non-NFC strings instead of normalizing them, so canonicalization never mutates attested data.
- Large ints are admitted only when they equal the exact value of their canonical double text (fixed-point property).
- Ledger storage is SQLite WAL with `BEGIN IMMEDIATE` (cross-process single writer), `synchronous=FULL`.
- The fencing token is per-resource and increments on every grant. Renew keeps the token. Release expires the lease.
- The ADR-143 thresholds (mutation ≥ 98.4%, CC ≤ 5) will ship as a `sovereign` profile, not the default (see build map).
- Hermes is used as a design reference only. **No Hermes code has been ported yet**, so there is no NOTICE.

### Built (evidence: `pytest` → 56 passed locally on Linux / py3.13; CI matrix configured for 3 OS × py3.12–3.14)
| Module | Proof |
|---|---|
| `serial/jcs.py` RFC 8785 | RFC reference example, UTF-16 key-order vector, ES6 number vectors, hypothesis fixed-point + stdlib agreement |
| `serial/afser.py` AF-SER-V1 | roundtrip; two-arm: tampered read-back purges everything |
| `comb/ledger.py` | chain from GENESIS_ROOT; 6 tamper modes caught; consistent forgery caught by signatures; 4 spawn processes × 25 appends → 100-event valid chain |
| `comb/hlc.py` | monotonic under wall-clock regression |
| `comb/leases.py` | exclusion, expiry takeover (token 1→2), zombie holder rejected by fence, renew/release |
| `comb/blobs.py`, `comb/enclaves.py` | content addressing, bitrot detection, promote-only-if-unchanged, immutable committed, quarantine, 7 unsafe-name two-arm cases |
| `crypto/keys.py`, `hive.py`, `cli.py` | init/verify/tail, tamper → exit 2, swapped host key refused |

### Known limits (not defects; scheduled)
- Enclave policy is enforced in-process and with permission bits only. OS sandboxing is M3.
- On Windows, the private-key file relies on the profile ACL. Hardware keys are M3.
- The ledger is single-host. Federation (CRDT/MST) is M5.

### Open questions for owner
1. Pillar 1 Google Doc is empty (1 KB).
2. License choice.
3. Provider keys available for M1 (needs ≥ 3 lineages for the 2-of-3 quorum).
