# Bounded resume capsule — M1 candidate

This slice provides derived context for one existing TaskEgg and restores an existing eligible worker claim. It does not decompose goals, schedule work, execute a provider, grant a tool, retry an inference or decide a gate verdict. Oviposition and the M1 exit test remain separate work.

## Source and packet contract

Use `build_capsule(hive, egg_id)` to build canonical UTF-8 JSON from one consistent SQLite WAL read snapshot. The service verifies the whole source ledger's hash chain and registered signatures, the signed hive identity and each selected TaskEgg declaration/signature. There is no model-generated summary.

The packet carries version/kind, `authority: "none"`, hive/genesis identity, exact head sequence/hash, task input/schema/state/digests, bounded dependency references, direct-parent outputs, current lease and last claim references, spend/receipt references and a proposed next step. It carries no issued capability body/signature or new grant. User-supplied task input or output is still untrusted data: this is neither a secret-redaction filter nor a public-export format.

For dependencies, the complete bounded ancestor closure includes IDs, egg digests, laid-event references, parents, states and artifact digests. Only direct parents' delivered/hatched outputs are inline; transitive outputs are deliberately omitted by contract. This is not silent pruning. Tasks/parents with missing or inconsistent required files are refused. Purged output is not exported.

Artifact bytes must match their recorded digest and canonical task envelope. Retained receipt request/response blobs (and v2 schema blob) must match their digest; the capsule carries references, not raw request/response bodies. This checks retained integrity, not full receipt replay or semantic correctness. Gate review still re-derives receipts, validates schema/output binding and controls admission. A signed state is not independent acceptance.

`verify_capsule(hive, raw)` rebuilds the packet against the current verified source and requires exact canonical bytes. It rejects stale heads, different hives, altered fields, ambiguous/noncanonical JSON, missing evidence and over-budget inputs. Unrelated ledger advances also stale a capsule. Lease expiry is checked at consumption, rather than changing packet bytes with wall time.

## Hard limits and failure behavior

| Scope | Limit |
| --- | --- |
| Canonical packet body | 32,768 bytes; caller may lower it |
| Verified source history | 4,096 events; 65,536 payload bytes/event; 2 MiB total payload bytes |
| Ancestors / direct parents | 32 ancestors; 16 parents/task |
| Longest dependency path | 8 edges, including shared DAG paths |
| Each read blob/artifact | 65,536 bytes |
| Claim / spend / receipt history for this task | 16 each |

The root is additional to the 32-ancestor limit. Overflow fails with `CapsuleError`; there is no truncation, summarizer fallback or provider request. Context file symlinks below the hive root are refused. Filesystem checks are best-effort in-process checks, not hostile-process isolation or an atomic multi-file snapshot.

History verification is linear within these limits; no O(1), zero-token, latency or savings claim is made. Event payload bounds are not a process-memory sandbox or a bound on every database metadata field. Larger hives/tasks need a separately designed verified checkpoint/splitting policy; raising a limit or skipping verification is not automatic recovery.

`Ledger.read_snapshot` uses a deferred WAL transaction, permits other connections to write, rolls back incidental SQL, and rejects nesting. Cleanup failure preserves the primary exception and discards the connection. It is a trusted-caller consistency helper. It changes no writer-transaction behavior or schema. A concurrent writer can make a successfully built packet stale immediately.

## Resume decisions

| Source state | Packet next step | Worker.resume |
| --- | --- | --- |
| Laid | claim_required | None; host must explicitly claim |
| Claimed, latest claim unspent | check_existing_claim | Restore only after all checks below |
| Claimed, latest claim spent, with or without receipt | reconcile_effect | ResumeBlocked; inspect evidence, never retry automatically |
| Delivered | gate_review_required | None; gate decides |
| Hatched | complete | None; do not deliver/infer again |
| Purged | quarantined | None; do not export rejected output |

`Worker.resume(raw)` restores only the same worker's existing live unspent Claim. It rechecks the exact head, signed source egg/capability, current worker/provider/model/profile grant, revocation, validity window, hatched direct parents and live fenced lease. The mutable lease row must agree with signed lease history; the capability cannot outlive it. Consumption returns the existing capability and fencing token without minting or appending anything. Subsequent normal inference/delivery APIs still recheck their own authority/fence.

An unrecorded staged/committed artifact for an undelivered task is a reconciliation error. Missing evidence never implies that an effect did not happen. Spent attempts remain blocked even if a response exists or the capability has unused budget. A later explicitly issued host claim is a distinct attempt and preserves prior spend references; capsule consumption does not create it. The slice prevents automatic replay through this API, not all possible deliberate host retries or provider-side duplicate execution.

## Interfaces

```bash
queen capsule build egg_<32-lowercase-hex> --hive /path/to/hive > capsule.json
queen capsule verify capsule.json --hive /path/to/hive
```

The CLI frames the canonical body with exactly one UTF-8 LF, and verify removes only that one LF. The Python API accepts the canonical body without framing. Both support `max_bytes` / `--max-bytes` bounded by the hard limit. Use a source-appropriate private destination; the CLI does not export to GitHub or Drive.

## Validation and remaining boundary

The candidate adds 43 offline cases: reopen/resume and single delivery, stale/tampered/ambiguous packets, unknown spent effects, missing blobs, lease/capability revocation/expiry/profile changes, unrecorded artifacts, dependency/output integrity, packet/history/dependency/attempt limits, shared-path depth, source-chain signer failure, concurrent writers, cleanup failure, symlink refusal and CLI UTF-8 round-trip. Fixtures are explicitly signed fixture receipts in test hives.

Local full suite on November 8: 366 passed, 9 skipped (7 historical archive checks with no private ZIP supplied; 2 credential-home checks unavailable in the local execution view). Ruff and strict mypy are required. Platform CI must establish its actual candidate revision and scope before qualification. No live provider call, cross-lineage review, runtime containment acceptance or M1 exit claim follows from these tests.



## November 8 post-merge qualification finding

The capsule landed in #18 (Verified signed 01e52d4); its PR matrix 42478326333 passed. Main run 42478678377 then exposed the existing claim binder's clock drift: its capability could expire after its lease. The capsule correctly refuses such a claim. QOS-0036 supplies an absolute issuance deadline; the resume check stays unchanged. Legacy malformed claims are not silently repaired. See HANDOFF and the QOS-0036 follow-up PR for current revision/CI evidence. The separate keyless canary failed before inference on a runtime-download HTTP 504, so there is no live verdict for this main revision.
