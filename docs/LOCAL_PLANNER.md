# Bounded local proposal producer (QOS-0041)

This candidate connects a real local proposal to the existing deterministic goal admission
and atomic task publication from #20. It stops at publication: no automatic worker execution,
model-managed tools, hosted fallback or model loading. LM Studio must already serve the
operator's exact loaded instance on a keyless loopback HTTP address. Lifecycle controls remain
the separate explicit commands described in LOCAL_MODELS.md.

## The first template catalog

The host selects a deliberately narrow item-note exercise, not a general planning language.
A brief has only a nonempty objective and one or two named source notes. Each note is at most
512 UTF-8 bytes, the objective at most 1000, the raw/canonical brief at most 4096. See
`examples/item-notes-goal.json`. The caller must choose an objective suitable for this catalog;
the implementation does not decide whether an arbitrary objective is covered or fulfilled.

The model proposes only local IDs, `extract_items` / `combine_items`, source IDs and parents.
All fields are required, unknown fields/types are rejected, and the response must be one JSON
object without duplicate keys, coercion, repair or prose stripping. Host validation requires
one extraction per supplied note, each without parents, and exactly one combination depending
on every extraction. IDs/dependencies must be unique and source coverage exact. The model
cannot invent sources, instructions, schemas, tools, ploidy, budgets or policy.

Host templates expand the accepted graph into existing TaskEgg inputs: extraction instructions
and source data, then combination instructions and source IDs; closed item/quantity/source
output schemas; diploid ploidy; tools=[]; stimulus=0.9. Existing profile, schema, DAG and budget
admission runs again before publication. Template identity covers the instructions, planner
system prompt, worker schema and policy constants. A changed template refuses old publication
rather than silently interpreting it under new rules. Original model JSON and compiled task
JSON remain distinct evidence. This constrained exercise demonstrates plumbing and admission,
not general goal decomposition or semantic correctness.

## Resource accounting before the first request

Defaults are an outer ceiling of four calls and 2560 requested completion tokens, split into:

| Phase | Calls | Requested completion allocation |
|---|---:|---:|
| Planning | 1 | 1024 |
| Workers, reserved for later explicit execution | at most 3 | 512 per task, at most 1536 |

The accepted ranges are 2–3 tasks, 128–2048 planner output tokens, at most four total calls
and at most 3584 total requested completion tokens. Configuration must cover all fixed pools
before any inference is admitted. Surplus/unused allocation is not borrowed across phases.
A one-note/two-task case can use three calls and 2048 tokens with the default planner ceiling.
Shorter replies, failed calls and uncertain effects do not refund their requested reservation.

`goal.run_prepared` records the exact host brief, model/endpoint, allocations, template/schema
hashes and encoded request hash/size before a one-call scoped capability is issued. Authority's
existing writer transaction checks both the capability and this run; worker spends also check
the existing per-task/published-goal limits. Replacement capabilities cannot reset lifetime
usage. Route/model changes, tools, missing/inconsistent run tags and oversized reservations
fail closed. Trusted host code can create other goals/grants: this is in-process accounting,
not OS containment or a global machine quota.

Tokens here mean requested output ceilings. They do not measure input, wall time, money,
energy or peak memory. Serialized request bytes are capped at 8192, not described as tokens.
The local planner additionally requires nonnegative integer usage and reported output no
greater than its reservation when accepting a real receipt. Usage is backend-reported, not
independently attested. Weight bytes and loaded context do not prove peak VRAM.

## Source custody, publication and recovery

The existing witnessed provider records exact request/response bytes in content-addressed
storage and a signed v2 receipt. Acceptance replays that receipt, verifies its run-scoped
capability spend, actor, provider/model/endpoint, exact request and schema hashes, and compiles
the recorded response. Multiple receipts claiming one planning spend are ambiguous and refused.
Signed `goal.plan_source` binds the original receipt, prepared run, template and compiled blob.
It is provenance/admission evidence, not a semantic verdict.

Only that exact source-bound graph, objective and worker budget can be published for the
prepared goal. Existing signed eggs plus `goal.planned` commit atomically. Reopening the hive
rechecks chain signatures, raw receipt, compilation, publication and task identities. Historical
standalone/manual plans keep their existing contract; they are not relabeled as model-produced.

| Readback state | Meaning / permitted next step |
|---|---|
| PREPARED | Intent exists, no recorded spend. Inspect before choosing a continuation; CLI `plan` never restarts that ID. |
| UNKNOWN_AFTER_SPEND | Reservation exists without receipt. Keep pending; never regenerate automatically. |
| RECEIPT_RECORDED | A response receipt exists, not yet accepted as a proposal. Inspect/replay it; a rejected response is not retry permission. |
| SOURCE_ACCEPTED | Original receipt and host expansion bound. Explicit publication may proceed. |
| PUBLISHED | Complete graph read back. Workers remain a later explicit operation. |

Readback labels grant no authority. Lost intent/source/publication returns may follow a commit;
inspect actual ledger/blob effects first. Explicit receipt recovery never calls a model, and
explicit publication is idempotent for identical committed evidence. Unknown effects remain
unknown. `semantic_goal_acceptance` is always `not_assessed` here; `regeneration_allowed` is
always false. Corruption, incomplete provenance and mismatches refuse status/admission.

## Operator commands

```sh
queen goal preview examples/item-notes-goal.json --model EXACT_LOADED_INSTANCE
queen goal plan goal_items examples/item-notes-goal.json --model EXACT_LOADED_INSTANCE --hive /path/to/hive
queen goal show goal_items --hive /path/to/hive
queen goal recover goal_items --receipt-seq RECORDED_SEQ --hive /path/to/hive
queen goal publish goal_items --hive /path/to/hive
```

Preview validates/encodes locally with no hive, capability, model call or publication. It reports
request/schema bytes and allocations. It honestly leaves native token count/context fit unknown:
qualify the actual chat template/tokenizer plus output headroom against loaded context before
the authorized real test. The CLI does not automatically prove context fit or enforce a GPU
quota. `plan` is an explicit one-request effect followed by admission/publication, never workers.
No client injection in real planner calls; no proxy, redirects, credential lookup or retries.

## Qualification and limits

53 new offline cases cover malformed graphs/briefs, budgets before effects, provenance/corruption,
wrong-run and duplicate receipts, replacement/concurrent capabilities, lost response/commit
returns, template mismatch and publication/readback. Fixture planner → three workers → existing
gate also exercises all four reservations and receipt/output binding; it is explicitly fixture
evidence. Local full suite: **571 passed / 9 skipped** (seven absent historical archive cases,
two local credential-home restrictions). Ruff check/format and strict mypy pass.

Exact candidate CI and the separately authorized one-request local planning witness are pending.
Private local model inventory and receipts must remain outside this public repository. A real
planning receipt would establish that observed producer path, not independent model identity,
semantic goal quality, worker execution, M1 exit or frozen Astra containment acceptance. The
next slice must explicitly build the bounded worker request path from verified capsules and
define a separate source/quantity/completeness oracle before claiming end-to-end goal success.
