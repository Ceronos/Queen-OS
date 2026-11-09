# Bounded item workers and explicit receipt recovery (QOS-0042)

This extends the first LOCAL_PLANNER.md catalog through explicit real worker requests and
the deterministic gate. It does not schedule general agents or supervise an inference engine.
Hermes remains architectural reference. Frozen Astra v65 remains separate/NO-GO.

## Selection and authority

`Worker(goal_id=...)` filters readiness before selecting a task or creating its lease/capability.
The bounded path re-verifies the witnessed planner source, host expansion and exact published
task membership; an unsupported or unpublished goal is refused before worker selection. Any
in-flight task requires explicit readback rather than automatically reclaiming it. The existing
legacy default worker still sees all goals; callers must select a goal to opt into this filter.

Each selected task receives a five-minute lease and the existing diploid profile: no tools,
one call, at most512 output tokens, exact original provider/model. No lease renewal, new planner,
model load, hosted fallback or retry is automatic. The prepared request names the original
claim/capability/fence and fixed expiry. A later claim cannot migrate the prepared request.

Inside the authority spend transaction, source-bound workers require the current prepared
token, actor, latest claim, live lease/fence/expiry and exactly512 reserved output tokens.
One task spend is allowed across all capabilities for that task, including replacement claims.
Concurrent reservations cannot both win. Existing whole-goal ceilings remain: one planner
request/1024 plus up to three workers/1536 = four calls/2560 requested completion tokens.
Short, rejected, failed, timed-out and unknown replies do not refund or reset those reservations.

## Exact request provenance

`work prepare` claims a ready task in the selected goal and builds a bounded current capsule.
It records `worker.request_prepared` immediately after the capsule's signed head, with the
capsule/wire/schema/contract hashes, publication/run hashes, actor/token/fence/expiry, exact
provider/endpoint/model and512-token ceiling. Both capsule and wire bytes are retained locally
in the blob store. Stable task operation IDs prevent replacing the request with a new capsule.
Lost preparation returns require inspection; they are not permission to claim again.

The HTTP prompt contains the host-owned task input and accepted direct-parent outputs only.
It omits ledger history, signatures, leases, capabilities and transitive outputs. The system
instruction treats note/parent contents as data. A native JSON-schema request is required,
temperature0, serialized body <=8192bytes; no repair, trimming or schema downgrade occurs.

Recording the request advances the ledger, so the preparation capsule immediately becomes
historical. `verify_recorded_capsule` re-derives its exact verified bounded prefix and source
bytes for provenance only. It does not restore authority. Normal `verify_capsule`/`Worker.resume`
continue requiring the current head, mutable lease agreement and no unrecorded artifact.
The inference hook replays the prepared capsule/request; source-bound goals cannot bypass
this binding by using generic inference or a different endpoint/model/system/request body.

## Context qualification

The byte bound is not a token or memory guarantee. Preview the exact prepared request and
obtain actual prompt-template/token counts and loaded context from the existing backend.
Retain a canonical operator measurement object (local/private):

```json
{"v":1,"request_sha256":"<exact prepared wire SHA-256>","model":"<exact instance>","provider_kind":"local","context_tokens":2048,"prompt_tokens":200,"schema_tokens":100,"method":"operator_backend_tokenizer"}
```

The numbers above illustrate the fields, not measured values. Count the backend-formatted
system/user prompt and conservative schema overhead separately; require
prompt + schema +512 output +128 headroom <= current loaded context. A measurement for
another request/model is refused. The host records its retained proof hash and counts in
`worker.context_qualified` before spend. Counts are operator/backend reports, not independently
attested by Queen-OS. A fabricated report remains a trusted-host failure, not evidence of fit.
The code does not infer context fit from a boolean or silently truncate an oversized request.
Fixture measurements/receipts remain explicitly fixture-classified and production-refused.

Transport timeout is at most45s and below the remaining claim lifetime with2s headroom.
Timeout does not establish that the backend stopped computing: the attempt remains spent.
Input use, billed USD, GPU allocation, peak VRAM, backend cancellation, hostile processes and
inference internals are not bounded or attested by this in-process slice.

## Response, recovery and gate

Execution records the original raw request/response and signed v2 receipt before delivery.
The model JSON is delivered exactly; no expected-answer substitution or output repair occurs.
Receipt provenance includes the original actor/token, one exact spend, request/schema hashes,
provider/model/endpoint, run hash and512 reservation. Local usage must be present, nonnegative
and within the requested output ceiling. Ambiguous/missing evidence fails closed.

Explicit `work recover --receipt-seq ...` can restore the existing live claim solely for
delivery of a known verified response. It never issues a new capability, extends a lease,
repeats inference or refunds spend. Expired, revoked, replaced, foreign-actor or foreign-goal
claims refuse recovery. A spend without a usable receipt remains UNKNOWN; inspect, never retry.

If staging succeeded but the delivery append did not return, recovery reads the exact
canonical artifact and digest and appends only the missing fenced delivery, without repeating
staging. Different orphan bytes are preserved and refused. Recorded delivery/terminal outcomes
are read back against actual artifacts. Status rechecks committed bytes and the passing gate
evidence, including the source-bound oracle, before reporting an all-hatched goal.

The oracle `item-note-lines-v1` is declared before any worker call. Every source note must
contain one or more exact lines `Item NAME; quantity INTEGER.` (ASCII name1..64 characters,
signed integer up to six digits; no leading zeroes apart from zero). Unsupported/ambiguous
notes refuse before claims/calls. This is a synthetic catalog, not a general semantic judge.
The gate compares the multiset of exact `(source_id,item,quantity)` triples: missing, extra,
duplicate, altered-source, renamed or changed-quantity items fail. Combination must preserve
the complete expected union; item order may change. All original signature, digest, schema,
exact-response and quorum checks remain controlling. Wrong output is quarantined/revoked;
the child remains blocked. Deterministic oracle evidence is producer evidence, not an
independent containment verdict or broad competence claim.

Unrecorded promotion/quarantine effects are a remaining manual reconciliation boundary.
An artifact already in committed/ without a signed terminal verdict is preserved/HOLD; the
catalog gate refuses to overwrite it or relabel the promotion as a fresh purge. This PR does
not implement a gate filesystem-effect intent journal or expired-claim authority migration.

## Explicit commands

```text
queen work show --hive HIVE --goal-id GOAL
queen work prepare --hive HIVE --goal-id GOAL --worker nurse
queen work preview --hive HIVE --egg-id EGG
# Obtain and retain fresh backend context/tokenizer measurements for this exact request.
queen work execute --hive HIVE --egg-id EGG --worker nurse --measurement MEASUREMENT.json
# Only after actual receipt readback if an earlier return was uncertain:
queen work recover --hive HIVE --egg-id EGG --worker nurse --receipt-seq SEQ
```

`execute` makes one explicit call and, on a known successful receipt, delivers/reviews that
task. It never loops across a goal. Prepare each next task only after the prior gate outcome.
`show`/`preview` perform no inference. `recover` performs no inference or authority issuance.
Runtime permission remains an owner/manual decision; these commands do not authorize hourly
automations or consume the separate Sol approval.

## Exact-source qualification and bounded local result

Sourcea54fd72f97ed081c963477f6301107a34d843cd9, tree90bec3612dd3c318538df8ee0b538fbd9c06d681:
all115 public blobs matched the isolated source. Full local619 passed/9 existing skips;
ruff/format and strict mypy41 plus canary-script types pass. CI42597006552 attempt1 passed all13
jobs: Linux x64/ARM64, macOS, Windows × Python3.12/3.13/3.14, plus actionlint. Checkout logs and
Git parents identify tested mergeb08bce94cd4b9a162e28131a01999ad97342bd91 (56ab8aa + a54fd72),
with the same tree. Sample ARM64:621 passed/7 archive skips; Windows:620/8 (one POSIX-only skip).
No workflows or strict canary oracle changed.

The existing real planner/publication was continued, without another planner call. Exactly
TWO new local worker requests ran, each512 output maximum/no tools/no retries. Both native
preflights measured167 prompt+86 schema+512 output+128 headroom=893, below loaded2048 context.
Actual backend-reported prompt usage167 matched each preflight.

- Worker1:369 reported output tokens,stop; original raw receipt replay, exact model JSON
  delivery and deterministic source/item/quantity/completeness gate passed. Artifact promoted.
- Worker2:HTTP200,512 reported completion tokens including505 reported reasoning tokens,
  finish_reason=length, empty content. Signed v2 rejection/raw custody retained. Offline
  replay confirmed structured rejection; no artifact/delivery was manufactured or promoted.
- Dependent combination was NOT started. Explicit receipt recovery and further preparation
  refused, with no new ledger events during those refusal checks. Reopen verified29 signed
  events. Whole goal retains3 calls/2048 requested completion tokens including its original
  planning request; reservations are not refunded or recycled.

This is one successful worker/gate plus an observed fail-closed model rejection. It is NOT a
successful end-to-end goal or M1 exit. Completion/reasoning budget exhaustion is reported by
this backend; native context fit is a separate successful check. Detailed private model
inventory, raw responses, reasoning text, receipts and hive stay local. No private originals
were exported. This qualification amendment changes docs only; final-head CI/blob equality
must be verified before carrying forward the source result. Do not repeat either worker or
its completed planner. QOS-0043 records the next gap.

## Proposed follow-up: explicit reasoning policy (not implemented)

Before another run, qualify a host-owned reasoning policy for the exact selected backend/model
and bind it into prepared run/request hashes and receipt replay. LM Studio documents advertised
[reasoning capabilities](https://lmstudio.ai/docs/developer/rest/list) and a reasoning setting
on its [native chat route](https://lmstudio.ai/docs/developer/rest/chat). That does not establish
that the current OpenAI-compatible schema route accepts the same setting. Do not silently
change routes, templates, model defaults or signed requests, or treat a requested setting as
proof it was honored. Preserve schema/raw-receipt strictness and no-tool/no-retry boundaries.

An offline extension must refuse unsupported/mismatched policy before spend, retain reasoning
versus visible-output usage honestly, and preserve old source interpretation. Then a fresh
separately authorized goal/budget can test the qualified policy. The spent task in this goal
must never be retried, re-signed into new authority or reset to create another attempt.

Agent: Sage (Codex)
Codex-Session: 01a1ab22-a4f2-7852-b510-5973fd1a4952
