# Offline recovery contracts for the existing ledger

These are producer regression checks against `comb/ledger.py` and `comb/leases.py`,
not a second store or a worker runner. All work payloads are synthetic. Keys are
generated locally by the tests. No provider adapter, model or live credential is
used. The initial test contribution did not change the production implementation.
The subsequent hardening extension is documented in `TRANSACTION_LEASE_RECOVERY.md`;
it changes transaction cleanup and lease lifecycle recording/readback, and adds
controlled abrupt-writer-exit tests.

| Boundary | Negative arm | Recovered positive arm / evidence |
|---|---|---|
| Lease grant before commit | Inject `RuntimeError` or `KeyboardInterrupt` after the real lease/event INSERTs | Reopen: neither row nor event remains. A new grant receives token 1; its fenced append and signed chain verify. |
| Append committed, readback unavailable | Inject `OSError` in post-commit readback | Reopen: the signed result exists exactly once. Read it, then append a separate reconciliation event referring to its stored ID. |
| Expired and superseded worker state | Reopen at the exact expiry boundary; reject the old fence both before and after takeover/reopen | Rejections preserve the head. The new token advances and admits a valid signed completion. |
| Noncanonical result | Reject a NaN payload under a current fence | Reopen with a regressed clock: the next valid append uses the next sequence, links to the persisted head, advances HLC, and the lease remains renewable. |

The second case is an important caller contract: **an exception does not establish
that an append had no effect**. Reconcile the stored event before considering a
retry. The test's `operation_id` is an application correlation label, not a ledger
uniqueness constraint. This change adds no automatic deduplication, exactly-once
execution, projection/capsule recovery or external-effect reconciliation.

## Reproduce without inference

After installing the declared development dependencies in an isolated environment:

```sh
python -m pytest tests/test_recovery_contracts.py --ignore=tests/live -q
python -m pytest --ignore=tests/live -q
ruff check src tests scripts
ruff format --check src tests scripts
mypy
```

Keep keyring access disabled (`QUEEN_DISABLE_KEYRING=1`), use a fresh `QUEEN_HOME`,
and remove provider keys/live-target settings from the test subprocess environment.
The full suite's credential-storage fixtures require a temporary directory outside
any Git worktree. On hosts whose default temp directory has a Git ancestor, pass
`--basetemp` pointing to a fresh non-Git directory; do not weaken the refusal check.

## Observed validation and limits

2026-11-07, Linux / Python 3.12.3: five new cases passed within the full **115-test
offline suite** (110 before this contribution). Ruff, format and package mypy also
passed. The preceding CI safeguard, commit
`174f36a95473201c5717725ac42140fa05a1fd8f`, passed all nine OS/Python jobs in
[run 42370239866](https://github.com/Ceronos/Queen-OS/actions/runs/42370239866).
Those prior results do not establish cross-platform results for these new tests;
check this contribution's own CI.

The database, signatures, rollback and connection reopens are real. Faults are
controlled Python exceptions; reopen is clean. There is no claim of abrupt
process-kill, power-loss, damaged-media or remote-provider recovery from these
initial cases. The later extension separately tests abrupt writer exit. A fence
checks a current resource token/expiry; it is not an actor capability or OS
boundary. Independent containment acceptance, the separate research fresh-session
adapter, aggregate budgets and real worker cancellation remain unresolved. Existing
real-agent NO-GO decisions remain in force.

## Next implementation contract

Continue the existing TaskEgg/capability and worker-claim work. A future worker
must recover from stored evidence, reject stale grants, correlate interrupted
operations and avoid replaying uncertain external effects. Define an explicit
idempotency/reconciliation contract before adding retries. Keep provider execution
behind separately accepted prerequisites and explicit scope; this test PR does not
authorize it.
