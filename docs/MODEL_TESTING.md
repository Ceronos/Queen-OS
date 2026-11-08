# Lower-cost model testing — options and evidence contract

Research snapshot: November 8, 2026. These are test routes and proposals, not new standing model authority. Choose a concrete model/revision/endpoint and bounded call plan before a fresh witness.

## Prefer evidence reuse, then existing local models

| Route | Useful evidence | Cost/coverage boundary |
| --- | --- | --- |
| Fixture and negative-case suite | Graph admission, custody, refusal, concurrency, budgets and recovery | No inference cost; cannot establish model quality |
| Offline replay of a real retained receipt | Exact request/response signatures, decoding, schema and output binding | No new inference; does not prove current provider availability |
| Existing LM Studio model | Fresh local generation through the existing OpenAI-compatible adapter | Avoids vendor per-token billing; local memory, power and time remain resources |
| Existing keyless Ollama canary | Small-model inference path and its explicit answer oracle | A small single-answer result does not qualify a strategic planner |
| Existing llama.cpp or vLLM server | Another local inference route | Verify installed version, schema dialect/model and hardware fit first |
| Subscription-funded API credits | Potentially fund a small paid-API witness | Owner/account eligibility and secure key setup are still required |
| Research/community checkpoints | Controlled comparison of emerging model variants | Check exact source/license/quantization/runtime; downloads/training/installations are separate work |

Use a strong reference output once to seed multiple deterministic replay/perturbation cases, labelled as derived fixtures. Generate malformed graphs, cycles, duplicate keys and budget attacks offline rather than paying a model to produce each failure. This reduces harness development cost without mislabelling replay as fresh inference.

## Local protocol compatibility

LM Studio documents JSON-schema response_format on /v1/chat/completions and an OpenAI-compatible /v1/models listing. It also warns that model support varies, especially below 7B parameters. Grammar-constrained JSON still needs schema, graph, budget and semantic checks. [Structured output](https://lmstudio.ai/docs/developer/openai-compat/structured-output), [endpoints](https://lmstudio.ai/docs/developer/openai-compat).

llama.cpp converts a supported subset of JSON Schema to grammars; the model does not automatically see the schema as prompt instructions. [Primary documentation](https://github.com/ggml-org/llama.cpp/blob/master/grammars/README.md). vLLM documents structured outputs and backend-dependent behavior in its compatible server. [Primary documentation](https://docs.vllm.ai/en/stable/features/structured_outputs/).

Queen-OS already has lmstudio, ollama, llamacpp and vllm presets. Current lmstudio/llamacpp/vllm presets do not advertise native structured-output support; a generic compatible endpoint is not automatically qualified for that mode. A narrowly tested preset/negotiation update can follow an installed-version witness. Do not silently remove a schema requirement or relabel free-form JSON as native constrained generation. No provider flag or live workflow is changed by the planning PR.

Weight-file size is not peak VRAM. Allow for context/KV cache, buffers and runtime overhead; measure the actual loaded model with a short fixed context before assigning a “half-card” target. Small or aggressively quantized variants are candidates to compare, not assumed quality equivalents. A fresh local witness is not a fresh-session containment proof.

## A legitimate subscription route

OpenAI documents API-credit benefits for eligible paid Pro and Business subscriptions. Activation links the owner subscription to an owned API organization with the same email, with account-specific eligibility and cycle expiry. The benefit does not increase signed-in Codex limits or cover Codex API-key usage. Eligibility is not established by this document. [Official benefit and eligibility](https://developers.openai.com/api/docs/guides/chatgpt-api-credits).

This can potentially fund a normal API witness without purchasing additional credits; it still uses the documented API/key path. Existing subscription/session credentials are not exported or repurposed as provider keys. No purchase, account linking or auto-recharge is performed here.

## Preserve the approved Sol witness

The owner-approved target remains gpt-6.1-sol: ONE request, 1024 total completion tokens, USD 0.05 allowance, no tools/retries, fixed synthetic input and offline evidence replay. Current official model documentation lists structured-output support and standard token pricing; this is not proof of this account's access. [Model documentation](https://developers.openai.com/api/docs/models/gpt-6.1-sol).

Key setup remains owner-controlled in the live-inference environment. The one-use workflow's exact-SHA, expiry, environment and first-run guards stay in force. Main moved after the original bb99eac approval: bind a new exact revision decision before dispatch. If the fixed expiry passes before setup, prepare a new concrete scope rather than bypassing it. Do not consume the first-run slot to test key presence.

A qualifying witness records exact model/quantization/server version, source revision, request cap, run/attempt, raw exchange custody and signed source, response-schema status, task/graph/budget result, semantic oracle result, token/time observations and limitations. Keep received failures. Replay without a credential, and report current availability separately. No model test, model load, download or service startup is executed by this document.

