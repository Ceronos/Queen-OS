# Transaction and lease recovery hardening

This extends the offline recovery tests with production fixes in the existing
ledger/lease modules. It adds no runner, provider call, automatic retry or second
state store. It traces to the QueenStore and atomic-leases rows in the build map.

## Reproduced failures and resulting contract

| Boundary | Before | This change |
|---|---|---|
| SQLite COMMIT fails | COMMIT was outside the exception handler; a deferred-constraint failure left the connection in a transaction | Include COMMIT in cleanup handling. Roll back only while SQLite reports an open transaction, then propagate the original error. |
| SQLite already rolled back | A redundant ROLLBACK masked the original integrity error | Preserve the original failure and allow the next transaction to proceed. |
| Cleanup also fails | Cleanup replaced the primary error | Preserve the primary error, attach a reopen/reconciliation note, and attempt to close the failed connection. Never report success or retry automatically. |
| Lease duration | Renewal accepted zero/negative values; acquisition and renewal also admitted bool/float values or failed inconsistently | Both require a positive integer, excluding bool. Invalid input is rejected before changing a row or event. |
| Renewal audit | The lease row changed without a corresponding event | Update the row and append `lease.renewed` in the same transaction; payload binds resource, token and new expiry. |
| Lease acknowledgement | Grants/releases returned without the ledger's post-commit event readback | Grant, renewal and release all use the existing event hash/signature readback before acknowledging success. A readback error remains an uncertain effect requiring readback/reconciliation. |

Renewal continues to set expiry to `now + ttl_ms` while preserving the live fencing
token. A shorter duration can shorten the lease; this is not a monotonic extension
promise. Expired or superseded tokens cannot renew the current grant. A fence is
still a resource token/expiry check, not an authenticated actor capability.

## Compatibility and recovery rules

- No SQLite schema or signed event-header version changes. Existing databases and
  earlier signatures remain readable; no history is rewritten or backfilled.
- Each successful renewal now adds one event. Consumers must handle
  `lease.renewed` alongside grants/releases. Historical renewals that predate this
  change cannot be reconstructed from nonexistent events.
- Callers supplying bools, floats, strings, null or nonpositive durations now get
  `ValueError`; typed callers using positive integer milliseconds retain the API.
- A lease readback exception can occur **after the row and event committed**.
  Reopen/read the actual lease and signed events before deciding what to do.
  Reacquiring is not harmless deduplication: it can advance the fencing token.
- A cleanup failure requires a fresh connection and evidence reconciliation.
  Neither a raised exception nor a cleanup note proves the absence of an effect.
- This adds no operation-ID uniqueness constraint, external-effect reconciliation,
  aggregate budget enforcement, worker authorization or exactly-once execution.

## Evidence

The pre-fix regression receipt contains 23 failing cases. These cover distinct
failure paths and the proposed validation/audit contract; they are not 23 distinct
vulnerabilities. Real SQLite deferred-constraint and automatic-rollback errors
establish the transaction defects. Cleanup/readback errors use explicit, limited
fault injection with real database writes and generated signing keys.

Two additional tests spawn a synthetic writer and call `os._exit` at a controlled
boundary, bypassing connection close and Python cleanup. The parent requires the
expected exit code before accepting the readback evidence:

1. Exit after the lease row and signed grant are inserted but before COMMIT:
   reopening finds neither; a fresh grant receives token 1 and can write.
2. Exit after an event COMMIT but before post-write fetch: reopening finds the
   single signed effect; the controller reads it and appends a distinct
   reconciliation event instead of repeating the effect.

Local observation, 2026-11-07, Linux / Python 3.12.3: **140 offline tests passed**,
versus 115 before this extension; Ruff/format and package mypy passed. Baseline
production-mode hive init and signed-chain verification also passed without any
inference. This contribution's OS/Python matrix must be checked on its own PR.

Reproduce the focused tests with:

```sh
python -m pytest tests/test_transaction_lifecycle.py tests/test_lease_lifecycle.py tests/test_process_recovery.py --ignore=tests/live -q
```

Use the clean environment and full-suite commands in `RECOVERY_CONTRACT.md`.
For these three files, all keys and workers are synthetic; no live credentials,
keyring access or network inference is needed.

## Limits and next work

Abrupt process exit is stronger evidence than a clean reopen, but it is not a
power-loss, kernel-crash, damaged-media or independently verified containment test.
The SQLite/OS/filesystem remain trusted; no hostile worker is launched. Producer
checks do not establish independent acceptance. The frozen v65 research candidate
and its real-agent NO-GO remain unchanged.

Continue the existing TaskEgg/capability and worker-claim implementation. Define
idempotency and uncertain external-effect handling before adding retries, and
require separate containment acceptance and a verified fresh-session adapter
before real-agent research comparisons.
