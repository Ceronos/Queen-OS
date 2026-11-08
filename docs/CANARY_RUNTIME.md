# Canary runtime acquisition contract — QOS-0039 / QOS-0005

Candidate prepared by Sage on November 8, 2026. This is CI infrastructure, not a model adapter,
a containment verdict, or a new live-run grant.

## Source and byte boundary

`governance/canary_runtime.json` pins the public upstream
[Ollama v0.40.15 release](https://github.com/ollama/ollama/releases/tag/v0.40.15).
The GitHub release-asset metadata observed November 8, 2026 reports:

- Asset: `ollama-linux-amd64.tar.zst`, Linux x86-64 only.
- URL: `https://github.com/ollama/ollama/releases/download/v0.40.15/ollama-linux-amd64.tar.zst`.
- Bytes: `1543547172`.
- SHA-256: `628c018404a4206493efd38e46251c154ede5141b8b8dc85c659b3b027c47379`.
- Release published: `2026-11-03T22:52:31Z`.

This is a committed digest derived from dated upstream metadata, not an independently verified
publisher signature. Pin updates require a reviewed source change; redirects cannot change the
accepted bytes. JSON pin parsing refuses duplicates, unknown fields, wrong versions/platforms,
non-HTTPS/nonrelease URLs, malformed digests and invalid size/type bounds.

The stdlib helper invokes curl with a fixed argument list, ignores user curl configuration,
permits HTTPS redirects only, bounds connection time to 15 seconds, transfer time to 120 seconds,
process time to 135 seconds and response size to the pinned byte count. No shell, auth flag or
installer is used. It allows three acquisition attempts at most, with 5/15-second backoffs.
HTTP 408/429/500/502/503/504 and selected transport interruptions are retryable. A short nominal
200 response is also retryable. Full-size wrong hashes, oversize, certificate failures, other
HTTP errors and local I/O/readback failures are terminal. Inference is never retried here.

Each attempt first records an IN_PROGRESS entry, writes into a fresh exclusive temporary
directory, then reads the actual file size/hash. Partial bytes are discarded between attempts.
Only exact size/hash plus a successful HTTP 200 transfers the file into its accepted path.
Existing bytes must verify exactly or remain refused and untouched. Symlinks/nonregular files
are refused. If a receipt write fails after archive publication, the step fails and extraction
does not run; no success is inferred from an interrupted producer. This is a single ephemeral
runner boundary, not protection against a hostile same-account process or filesystem races.

## Runtime and evidence boundary

Only a successful acquisition step permits tar/zstd extraction under RUNNER_TEMP. No sudo,
system service installation, host driver setup or live install.sh execution is needed. The
private runtime bin directory supplies subsequent steps. Client version and bounded local
server-version response must match the pin before model acquisition. An unexpected existing
server version fails rather than silently accepting it. This version check is not process
attestation. The large upstream archive and extraction layout have not been executed locally.

The original model pull retry block is retained. The original two real-model calls, T=0,
16-token ceiling per call, system prompt, signed-artifact verifier and separate strict `bee`
answer gate are retained. Triggers remain main push/manual only; permissions remain contents:read,
with no secret references. Job timeout remains 20 minutes. Transport recovery does not promise
that all future canaries will pass or that a 0.5B model is semantically reliable.

The always-run runtime artifact contains only:

1. `runtime-acquisition.json`: committed pin, fixture flag, attempt ordinal/transport status,
   received byte count/hash, acquisition disposition and zero inference requests by the helper.
2. `ollama-version.txt`: pinned client version command output.
3. `ollama-server-version.json`: only the validated, normalized version field.

No raw curl errors, raw server response, server log, archive, weights, model text, vault or
credential content is exported by this diagnostic artifact. Model evidence keeps its existing
admission gate; always-run diagnostics do not admit an invalid/private evidence pack. The
phase summary distinguishes infrastructure, witnessed inference, CLI integrity and answer result;
a failed/skipped/missing phase is never labeled passed.

## Verification limits

`tests/test_canary_runtime.py` uses synthetic bytes and injected transport effects, not a model
or runtime. Fixture infrastructure records carry `fixture: true` and are unsigned producer
diagnostics; they are never passed to inference-receipt admission. Tests cover transient recovery,
exhaustion, checksum/size/permanent failure, source-pin refusal, preserved existing bytes,
unreadable effects, pre-transfer receipt failure, fixed HTTPS process invocation, phase reporting
and the workflow's diagnostic export boundary. CI additionally type-checks the helper.

A passing offline matrix does not establish successful upstream archive extraction or live
inference for this candidate. After a separately owner-approved protected main merge, inspect
the ordinary canary's exact SHA/run/attempt/phase results and retained evidence. Do not rerun a
failure automatically, relax the oracle or substitute CI for independent containment acceptance.
