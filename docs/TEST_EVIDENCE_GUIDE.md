# Interpreting test evidence

This note distinguishes source inspection from test execution when reviewing Queen-OS research reports. It is documentation only; it does not change any runtime behavior.

| Evidence | What it establishes | What it does not establish |
| --- | --- | --- |
| A test file is present in a repository | Assertions have been written | That those assertions passed |
| Implementation and tests refer to matching code paths | A source-level correspondence | Correctness under execution |
| A local test command exits successfully with retained logs | The specified tests passed in that environment | Production readiness or results on another host |
| A CI check reports success for a pinned commit | The reported check succeeded for that commit | Deployment, full coverage, or independent custody |
| A ledger event has an operation ID | A possible deduplication key | Exactly-once external effects across files, services, or jobs |

## Minimum reproduction receipt

For a reproducible test claim, record the repository, full commit SHA, relevant test paths, interpreter and dependency versions, exact command, execution environment, UTC time, exit code, and complete or retrievable output. Distinguish direct observations from statements copied from another report.

If a test was not executed, use **SOURCE_INSPECTED / TESTS_NOT_EXECUTED** rather than **TESTS_PASSED**. If an environment is inaccessible, say so; do not infer a host connection from a connector read.

## Cross-system boundaries

A database transaction and a filesystem promotion are not automatically one atomic operation. An acknowledgment failure can occur after a commit. Evidence for retry safety should therefore distinguish ledger deduplication, external side-effect idempotency, and reconciliation of partial commits. Any destructive fault injection or host-specific recovery test requires a separately authorized isolated environment.

This note is a review aid, not a security approval, release gate, or change to House governance.
