# HANDOFF → next engineer on Queen-OS

Updated November9,2026 by Sage/Codex. Claude remains unavailable; preserve his work/attribution.
This is manual owner-authorized construction. Hourly repository observation remains read-only.

## Verified baseline

Signed main56ab8aa46ea93966c010ec65d57743c119d233b2 (#23), tree0692b82e86ab12fdcef14c3eafc23aa4a92fbfad.
Main CI42591134510 all13 checks and keyless canary42591134428 passed. PR23-only owner exception
was consumed; it does not permit merging PR24. No other open contribution observed at start.

The completed planner/publication witness has one planning spend/receipt, three published tasks,
reported185 input/752 output tokens at a1024 output reservation, zero workers. Source075e6bf
code/test/workflow equality to final PR23 was verified. Do not repeat that planner call.
Private model inventory, runtime proofs and receipts remain local. LM Studio is the manual
focus; Queen-OS uses an existing backend, not its own inference engine. Hermes is reference.

## Current candidate: goal-scoped bounded workers / QOS-0042

Owner approved fixing goal-specific claims and known spent-receipt recovery, then implementing
explicit capsule-derived workers and a deterministic semantic gate on the existing published
goal. See BOUNDED_WORKERS.md for the exact contract, commands, oracle and recovery boundaries.
New workers/execution.py maps to existing worker/capsule/gate rows; no general agent scheduler.

Worker filtering occurs before claim effects. The explicit path verifies exact published task
membership and source. One immutable capsule/request per task, strict native schema, no tools,
512 output tokens, temperature0, exact provider/model/endpoint. Historical capsule replay is
provenance only; ordinary resume remains current-head/live/unspent. Context counts are retained
operator/backend measurements tied to request/model, not independent resource attestation.

Authority checks current prepared token/actor/claim/fence and one task spend across replacement
caps atomically before inference. Full goal still at most4 calls/2560 requested completion
including the completed planner. Failed/unknown calls remain spent, no retries/refunds/borrowing.
Known response recovery restores only the original live claim for exact delivery, without new
inference or authority. Orphan staging is read back before recording missing delivery; different
bytes are preserved/refused. Unrecorded terminal filesystem effects require manual reconciliation.

The declared item-note-lines-v1 oracle checks exact source/name/quantity/completeness/multiplicity.
Schema-valid wrong answers quarantine and revoke; no repair/substitution. Only accepted direct
parents enter the combine request. Status verifies committed bytes and terminal gate evidence.
This is a narrow synthetic goal, not general competence, OS containment or independent acceptance.

## Qualification / next

Baseline571 passed/9 existing skips and fresh signed genesis verified before changes. Initial
full implementation run610/9; further targeted worker/planner tests101 passed after recovery/status
hardening (48 new worker cases). Final full619 passed/9 existing skips; ruff/format and strict mypy41 plus canary-script types pass. PR CI pending.
No new real worker request has run at this checkpoint. The authorized witness is at most three
new local worker requests/512 output each on the existing goal, no tools/retries/replanning.

1. Finish final full checks and exact-source PR CI on Windows/macOS/Linux. No workflow changes.
2. Fresh selected-instance/context/tokenizer readback for each exact worker request. Keep private
   measurements local. Execute no more than three new requests; any uncertainty stops automatic
   progress. Reopen and verify raw receipts, exact delivery/oracle outcomes and whole-goal budgets.
3. Update qualification docs from actual results. If only docs change afterward, compare all
   code/test/example/workflow blobs to the witnessed source and recheck final-head CI.
4. Obtain a new PR24-specific owner cross-review exception/merge decision while Claude is absent.
   docs/ENGINEERS.md requires the other engineer's review; PR23 approval does not cover PR24.
   Preserve protected signed squash, exact-head checks and final signature/CI verification.

Sol remains deferred/no key/request; the old one-use bb99eac approval expires2026-11-10T00:00Z
and is not migrated here. No downloads, installs, hosted fallback, protected settings changes,
other-agent messages or changes to frozen v65/prototype. Real-agent containment remains NO-GO
and a fresh-session adapter/independent acceptance remain absent. Representative design, merged
code, tested integration and independently accepted runtime remain distinct states.

Read CLAUDE.md, docs/ENGINEERS.md and latest LEDGER/BUILD_MAP before edits. LEDGER append-only.

Agent: Sage (Codex)
Codex-Session: 01a1ab22-a4f2-7852-b510-5973fd1a4952
