# HANDOFF → next engineer on Queen-OS

Updated November 8, 2026 by Sage/Codex. Johnny assigns Sage construction leadership while Claude
is unavailable. Preserve Claude's work and attribution. Owner merge exceptions remain PR-specific.

## Verified main and retained history

Main is **9f294afcd46771772e35f419343161559cf12bfd**, Verified signed #20 squash,
tree **6f178fe3f78bf99dc21cece1ddde83eef964fc84**. Main CI **42484325300** passed all
13 checks; automatic keyless canary **42484325250** passed. These are dated producer results,
not general model competence or independent containment acceptance.

- #16: QOS-0008 structured JSON slice landed; streaming/general tools and live compatibility remain open.
- #17: one-use Sol witness and QOS-0034 controlled-clock test landed. No Sol dispatch occurred here.
- #18/#19: source-verified bounded capsule and absolute lease deadline correction landed under
  separate owner exceptions; no capsule/fence/expiry check was relaxed.
- #20: QOS-0037 deterministic goal/task validation, atomic publication/recovery and shared task/goal
  spend ceilings landed under its own exception. Strategic model production and live M1 exit remain open.
- Preserve main CI 42478678377 (01e52d4 ARM64 clock drift) and canary 42478678093
  (HTTP504 runtime download before inference). Later green does not relabel either failure.

## Current candidate: canary runtime acquisition (QOS-0039 / QOS-0005 remainder)

Johnny asks to resume the canary fix after repeated failure notifications. The historical audit
separates four strict-answer failures (QOS-0031, fixed by #13's system prompt), one early invalid
workflow configuration, and the HTTP504/incomplete runtime download. The latest known main
canary passes; the remaining acquisition weakness is still actionable.

This candidate replaces streamed install.sh execution with a committed Linux AMD64 release
URL, exact byte count and SHA-256. A stdlib helper records each attempt, retries transient byte
acquisition at most three times with fresh partial files, and publishes an archive only after
complete verification. Permanent, integrity and local readback errors stop. It never installs
or calls a model. The workflow extracts privately under RUNNER_TEMP, verifies client/server
versions and separates acquisition/runtime/model/inference/integrity/answer outcomes.

The two original inference calls, per-call 16-token ceiling, T=0/system prompt and separate
strict bee oracle remain unchanged. Existing model-evidence admission still gates its upload.
Only a small allowlist of infrastructure metadata is retained even on failure. No trigger,
permission, standing-order or notification setting is broadened. See CANARY_RUNTIME.md.

Forty new offline cases: local full suite **472 passed / 9 skipped** (7 absent historical archive
checks; 2 local credential-home fixture restrictions). Ruff/format, strict core mypy (37 files)
and explicit helper mypy (1 file) pass. Actionlint/platform CI and exact PR head/base evidence
must be checked on the candidate. No actual runtime archive/weight download, local installation,
model execution or workflow rerun occurred. The new extraction/live path remains unobserved
until a future approved protected merge and its ordinary main canary. No new merge approval.

## Model testing and next steps

QOS-0038 / MODEL_TESTING.md cover lower-cost testing. Local inventory remains in private work
receipts; no provider capability flag, service, weight download/load or witness was changed here.
Installed-version/schema/quantization/context evidence is needed for a bounded local witness.
Keep protocol compatibility, schema validity, graph/budget validity and semantic goal quality distinct.

Sol remains ONE gpt-6.1-sol request / 1024 total completion tokens / USD0.05 / no tools or retries.
The key is not configured; key setup remains owner-controlled. Original approval was pinned to
bb99eac. Main moved, so bind a concrete current revision decision before launch; expiry remains
2026-11-10 00:00 UTC. Never test key presence by consuming the first-run slot or silently renew
expired admission. This does not extend SO-0001.

1. Qualify/review this canary candidate and obtain its own owner merge decision while Claude
   is unavailable. Exceptions for #15–#20 do not cover another PR.
2. After an approved merge, inspect the ordinary main canary at its exact SHA/run/attempt.
   Preserve failure evidence; no automatic rerun or oracle relaxation.
3. Establish a bounded existing-local-model witness and replay evidence under a separate concrete scope.
4. Wire a strategic proposal producer through witnessed providers and prepare the real M1 goal/worker/gate
   exit experiment. A canned witness or fixture graph does not satisfy that milestone.

Read CLAUDE.md, docs/ENGINEERS.md, latest LEDGER and BUILD_MAP; baseline plus fresh signed hive
verification before changes. Work branches from main and lands through protected signed squash merges.
Frozen Astra v65 remains untouched/NO-GO; independent containment acceptance and a verified
fresh-session adapter are absent. Repository controls, CI and owner merge decisions do not replace
those gates. The hourly lane stays read-only/documentary; manual construction is separate.

Agent: Sage (Codex)
Codex-Session: 01a1ab22-a4f2-7852-b510-5973fd1a4952
