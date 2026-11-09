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

## Exact qualification / stopped experiment

Candidate sourcea54fd72f97ed081c963477f6301107a34d843cd9, tree90bec3612dd3c318538df8ee0b538fbd9c06d681.
All115 remote blobs matched. Full619/9 locally,48 new cases,target101,lint/format/mypy41 and
canary-script types pass. PR24 CI42597006552 attempt1 all13 succeeded. Actual tested merge
b08bce94cd4b9a162e28131a01999ad97342bd91 has parents56ab8aa+a54fd72 and the same tree.
ARM64 sample621/7; Windows620/8. No CI workflow or strict canary answer changed.

Exactly TWO new local workers ran on the already published goal; the original planner did not
repeat. Both fresh backend preflights167 prompt+86 schema+512 output+128 headroom=893 fit2048
context; actual reported prompt167 matched. First worker369 output,stop: raw receipt replay,
exact delivery and item oracle/gate promotion passed. Second worker512 completion including505
reported reasoning,finish_reason=length,empty content: signed structured rejection retained.
No delivery/artifact invented. Combination NOT started.29-event signed chain and refusal of
receipt recovery/further preparation read back; refusal checks added no ledger events.
Current goal3 calls/2048 reserved including original planner. No retries/refunds/new authority.

End-to-end goal/M1 exit did NOT pass. This is a successful first worker and a correctly retained
rejection/blocked dependency. Public docs contain only aggregate producer evidence; private
inventory/raw reasoning/receipts/hive stay local. QOS-0043: explicit host reasoning policy is
needed before another run; current native-schema route has no qualified reasoning control.

1. This final qualification amendment changes five docs only. Verify unchanged other110 blobs
   against witnesseda54fd72 and final-head CI before carrying its evidence forward.
2. Do NOT run the old witness again, even after expiry. A fresh separately authorized goal/budget
   is required for another attempt. Proposed next contract is in BOUNDED_WORKERS.md: advertised
   capability, explicit immutable reasoning policy, schema/receipt compatibility, offline guards
   then fresh native qualification. Do not assume native reasoning controls apply to /v1/chat.
3. PR24 fixes the two recovery/selection gaps and adds the bounded worker/gate foundation; the
   live end-to-end milestone remains open. Obtain a new PR24-only owner cross-review/merge
   exception while Claude is unavailable. PR23 approval does not cover this PR. Preserve protected
   signed squash and verify final signature/main CI; no merge grant exists at this checkpoint.

Sol remains deferred/no key/request; the old one-use bb99eac approval expires2026-11-10T00:00Z
and is not migrated here. No downloads, installs, hosted fallback, protected settings changes,
other-agent messages or changes to frozen v65/prototype. Real-agent containment remains NO-GO
and a fresh-session adapter/independent acceptance remain absent. Representative design, merged
code, tested integration and independently accepted runtime remain distinct states.

Read CLAUDE.md, docs/ENGINEERS.md and latest LEDGER/BUILD_MAP before edits. LEDGER append-only.

Agent: Sage (Codex)
Codex-Session: 01a1ab22-a4f2-7852-b510-5973fd1a4952
