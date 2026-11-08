# Local models: LM Studio lifecycle — QOS-0040

Queen-OS already routes witnessed inference through local-provider adapters. This slice adds
explicit operator controls for an existing LM Studio server to list installed LLMs, load a chosen
model with bounded context/weight settings, unload an exact instance and inspect current state.
LM Studio owns execution of the model weights. Queen-OS owns the operator request and its signed
coordination record. The harness does not yet bundle or start a private inference engine.

## Architecture and source

Hermes offers both a managed llama.cpp runtime and connections to existing local servers.
That is architectural reference, not evidence that Queen-OS has inherited its installer, memory
planner or supervision. No Hermes code, configuration, service or profile is changed here.
See [Hermes Local Models](https://hermes-agent.nousresearch.com/docs/user-guide/local-models).
An optional Queen-owned pinned engine supervisor can later sit behind the same lifecycle contract.

This backend uses LM Studio's documented native v1
[model inventory](https://lmstudio.ai/docs/developer/rest/list),
[load](https://lmstudio.ai/docs/developer/rest/load) and
[unload](https://lmstudio.ai/docs/developer/rest/unload) endpoints. Inference continues through
the separate OpenAI-compatible chat adapter and its receipt/budget/replay checks. The LM Studio
preset now advertises its documented [JSON-schema mode](https://lmstudio.ai/docs/developer/openai-compat/structured-output);
other generic compatible presets remain unqualified. A documented wire mode does not prove a
particular installed model/server produces acceptable output. Invalid output still fails admission.

## Explicit operator commands

Use an already configured keyless loopback server. No token discovery or authentication setting
change is performed by the lifecycle manager. An authenticated server is refused by this first
lifecycle slice; existing inference credential handling remains unchanged.

```sh
queen models list --base-url http://127.0.0.1:1234
queen models load 'exact-installed-model-key' --hive ./local-hive \
  --operation-id load-demo-1 --context-length 2048 --max-weights-bytes 17179869184
queen models status --hive ./local-hive --operation-id load-demo-1
queen infer lmstudio 'returned-instance-id' 'Return the requested synthetic JSON.' \
  --hive ./local-hive --base-url http://127.0.0.1:1234/v1 \
  --json-schema ./schema.json --max-tokens 512 --temperature 0
queen models unload 'returned-instance-id' --hive ./local-hive --operation-id unload-demo-1
```

Initialize the hive explicitly before mutating commands. Model keys and instance IDs are
reported by the local server; an exact available LLM key is required to load and an exact
currently loaded LLM instance ID to unload. No model search, fuzzy selection, download, automatic
installation, server startup, auto-eviction, automatic load during worker dispatch or hosted
fallback is added. Already loaded targets are refused rather than loaded again or implicitly
reconfigured. The host operator can separately choose an exact unload/reload. No model text or
task proposal can issue lifecycle commands. This CLI is not exposed as an agent tool.

## Bounds and transport

Lifecycle URLs accept HTTP loopback IPs only; localhost is normalized to 127.0.0.1 without DNS.
Root and /v1 spellings are normalized to the native API root. Remote addresses, URL credentials,
queries/fragments, unexpected paths and control characters fail before networking. HTTP clients
disable environment proxies and redirects, set 180-second I/O timeouts and bound each decoded
JSON response to 1 MiB. These are I/O bounds, not a guaranteed cancellation deadline for a model
load that already reached the backend. A failed response may follow a completed effect.

The normalized LLM inventory is bounded to 256 entries and 32 instances per model. Duplicate
keys/instance IDs, ambiguous JSON, invalid resource types, malformed or non-NFC identifiers and
unknown context ceilings are refused for a load. Requested context defaults to 2048 and may
not exceed the reported model maximum or the slice's 32768 ceiling. The default reported-weight
ceiling is 16 GiB; the operator may explicitly choose another positive ceiling up to 256 GiB.

The server-reported byte count is not a hash of the model file or a peak-memory measurement.
Backend selection, GPU layer placement, KV cache/buffers/projectors and actual VRAM/RAM fit
remain LM Studio/host responsibilities. The native loading API used here does not implement
a Queen GPU-layer controller. A loopback endpoint also does not attest backend implementation
or prove that another local client cannot affect it. No OS containment claim is made.

## Intent, uncertainty and readback

Each load/unload verifies the signed hive and records local_model.intent with the endpoint,
operation ID, exact target, resource settings, reported size and fixture classification before
one POST. The ledger transaction serializes claiming that operation ID and ends before any
network call. Intent readback must succeed before POST. Concurrent callers using the same ID
produce at most one POST; a repeated ID is refused even if a prior caller saw an error.

A valid reply records the returned instance ID; a separate GET then observes the requested
model/configuration or target absence. local_model.observation is a signed **producer** observation,
not independent acceptance or proof of causality. Lost/invalid replies or mismatched readback
retain UNKNOWN and never trigger a retry, cleanup, alternate model or configuration change.
Use models status with the same operation ID to read back current state without another POST.
A sole matching instance can establish current presence after a lost reply; multiple candidates
remain UNKNOWN. An earlier UNKNOWN entry is retained even after successful readback.

Operation IDs deduplicate requests within one hive. They are not a cross-hive/per-server lock,
a backend idempotency token, a lifetime resource reservation or a recovery grant. A new ID is
an explicit new operator action, never an automatic retry strategy. Other clients can race these
observations. Crashes can leave an intent whose POST never happened; readback must not invent it.

Injected HTTP transports are always fixture-classified and refused for production mutations.
All mocked lifecycle entries and inference receipts in tests carry fixture:true/fixture kind.
The normal transport is a real local backend; lifecycle events themselves are not inference
receipts, and model calls still require the existing scoped capability and spend reservation.
Raw server bodies/errors, local inventory and private runtime receipts are not published.

## Validation and remaining work

46 new offline cases cover endpoint refusal, source/resource/identity bounds, a signed load/unload
cycle, exactly-once ID claim under concurrency, lost replies, intent-readback failure, ambiguous
recovery, fixture refusal, native schema request encoding and exact recorded-response replay.
Local full suite: 518 passed / 9 existing environment/archive skips; ruff/format and strict mypy
(38 core files) pass. Platform CI and exact candidate head/base evidence belong to the PR.

Owner-approved manual local work is separate from the hourly read-only cadence. A proposed
first live witness uses one synthetic request, at most 512 output tokens and no tools/retries.
It needs a reachable existing server, exact model/instance/configuration, private producer
receipts and offline replay; success does not establish planning quality, M1 exit or independent
containment acceptance. Sol is deferred, with no key, call or allowance change.


### Dated candidate qualification — November 8, 2026
At source fbcd10003bf3c6d0af733ebd98961b1dff237674, PR CI 42501507581 attempt1
passed all13 jobs, testing merge 5cb3a73a783c3efbc94851f1304478571eba60e7 of main fe95a0f
and that head. Linux ARM64/macOS sample logs report 520 passed/7 historical-archive skips;
Windows 3.14 reports 519/8 (the existing POSIX-permission-only case also skips).

The owner's manual local grant was used for a real native unload/load at 2048 context and
exactly one synthetic structured request bounded to 512 output tokens with no tools/retries.
Producer state, signed response admission, the fixed-word semantic check and offline receipt
replay after hive reopen passed. Raw local inventory/runtime evidence remains private and
is not uploaded to this public repository. The selected model remains loaded at the short
context. This is one model/server witness, not broad compatibility, planning competence,
M1 exit or independent acceptance. No additional call is needed to qualify this docs update.
The final docs-only revision must still have its own CI and unchanged-code coverage checked.
