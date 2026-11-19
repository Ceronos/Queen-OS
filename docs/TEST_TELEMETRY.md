# Pytest lifecycle telemetry — first defensive slice (2026-11-18)

This first slice adds an **opt-in, metadata-only observer** for the existing
Queen-OS offline CI matrix and keyless canary pytest steps. It is not a sandbox,
red-team verdict, cryptographically attested provenance or an autonomous defender.
No existing inference scope, provider calls, approval/merge requirements, secrets,
or runner permissions are changed.

## Record and closure contract

For each observed pytest session the append-only JSONL contains `session_start` 
with GitHub run ID, attempt, commit, workflow, OS, Python version and selection
(`not live` or `live`); each test records `test_start`, setup/call/teardown phase
outcomes and observed `test_end`; the session records `session_end` with pytest's
exit code and unfinished count. There is no raw test output, model response,
traceback, full environment, credential, or parameter value. The test base name
is retained for grouping; a SHA-256 digest of pytest's full node ID correlates
parameterized cases without publishing parameter values. The digest does not
protect low-entropy parameter names from guessing.

Events are bounded (4 KiB each, 16 MiB journal), flushed and fsynced. After the
test phase an unconditional (`if: always()`) reconciliation step emits a JSON
summary and the job summary. Results are:

- `CLOSED_PASS`: session end was observed, every observed start has a matching
  end, and pytest exited zero. Only this result permits the telemetry audit step
  to pass. A test result alone does not establish sandbox containment.
- `UNCLOSED_OR_FAIL`: pytest exited nonzero, the session ended with open tests,
  or the session-end record was never observed.
- `UNOBSERVED`: evidence is missing or cannot be read at all.
- `INVALID_EVIDENCE`: malformed, oversized, duplicate or out-of-order events.

The evidence uploads with a 14-day retention window **even when a test step
fails**, provided the GitHub runner survives to execute the uploader. A killed
runner, cancelled workflow or lost machine can prevent upload; absence remains
unobserved, not success. The observer itself runs in the test process and is
therefore **not an independent integrity witness**. GitHub run/job completion
metadata must be reconciled from outside the test process in the next stage.

## Threats and immediate operating boundary

The 2026-11-17 Microsoft `agent-framework` PyPI compromise used malicious
startup hooks in versions 1.26.1 and 1.26.2. The current `pyproject.toml` on
main does not directly require `agent-framework`; this says **nothing** about
Astra, its virtual environments, downloaded wheel caches, transitive resolved
packages, or credential access. **Do not run an unknown Python environment with
production keys as part of an investigation.** Treat any confirmed affected
installation as possible credential exposure: stop related jobs, isolate the
host/runner, preserve minimal evidence, rebuild from trusted sources and rotate
accessible tokens from a known-clean environment.

Do not equate package-name pinning with supply-chain safety. Next-stage work:

1. Read-only inventory of Astra/agent host and CI resolved dependency sets and
   installation history (no secret contents); resolve any exposure and revoke
   affected credentials through owner-controlled accounts.
2. Trusted reviewed dependency lock files/hashes, offline wheel inspection,
   package provenance and startup-hook checks **before** any privileged Python
   interpreter; no floating unvetted install in credential-bearing jobs.
3. Out-of-band run/job completion reconciliation, monotonic deadlines, run IDs,
   attempt-specific receipts, abort/timeout/no-report states and bounded artifact
   retention. Independent evidence must not depend on the evaluated worker.
4. A disposable, no-secrets, network-restricted **internal red-team fixture lab**:
   simulate `.pth` hook insertion, dependency substitution, token-access attempts,
   interrupted test/worker processes, log truncation, poisoned receipts and retry
   races. Assess detection and containment without running live malware or
   targeting any external system.
5. Separate controller, operator and worker trust domains; short-lived scoped
   capabilities; egress allowlists and automatic quarantine on integrity/closure
   failure. No automatic merge on a green CI badge alone.

The Queen/worker can recommend and execute *preauthorized* isolation inside its
own bounded environment. It cannot attest to or repair a compromised host from
inside that same compromised host. All real-agent NO-GO / independent containment
gates remain unchanged until independently verified.
