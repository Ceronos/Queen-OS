# Structured output — QOS-0008 candidate

November 7, 2026. This implements schema-request codecs, local admission and replay; **live service/model compatibility has not been demonstrated by this contribution**. All new inference tests are explicitly fixture-marked in signed records and run in test hives.

## Request contract

`InferenceRequest(..., output=JsonSchemaOutput(schema))` opts into portable JSON-output contract v1. The constructor snapshots canonical schema bytes; later mutations to the original dictionary or a returned `.schema` dictionary cannot change the contract. No schema feature is silently removed or converted into prompt advice.

The conservative profile admits object roots, recursively typed closed objects (all properties required), arrays with typed items, primitive types, nullable type unions, primitive enums and descriptions. Every node must state its type. Bounds: 16,384 canonical schema bytes, nesting depth at most eight, at most 64 properties per object and 64 enum entries. The CLI also bounds raw schema-file input to 16,384 bytes. All other keywords, including references, defaults, regexes, combinators and external resources, are rejected locally. This is intentionally narrower than general JSON Schema or any vendor's full feature set.

After JSON parsing, local Draft 2020-12 validation is authoritative. Duplicate keys, nonfinite values, exponent overflow, noncanonical Unicode, prose/fences, invalid types, missing/extra fields and schema mismatches fail. No repair, coercion, default insertion, fence stripping or automatic retry occurs. Original successful text bytes are not rewritten just because their canonical value is validated.

## Native wire contracts

| Protocol | Native request setting | Admission and limits |
|---|---|---|
| Anthropic Messages | `output_config.format = {type: json_schema, schema: ...}` | JSON text output; no forced tool-call emulation. Accept one text block with `end_turn`; refusal/max-token/nontext responses fail. |
| OpenAI Chat Completions | `response_format = {type: json_schema, json_schema: {name: queen_output_v1, strict: true, schema: ...}}` | One textual choice with `stop`, no refusal/tool calls. The official OpenAI preset opts in. Other compatible presets default to unsupported; explicit programmatic adapter opt-in is required. |
| Gemini generateContent | `generationConfig.responseMimeType = application/json`, `responseJsonSchema = schema` | One STOP candidate and one plain text part; blocked/thought/mixed/tool responses fail. This does not migrate the adapter to the separate Interactions API. |
| Ollama native chat | `format = schema`, `stream = false` | Completed response with `done=true`, `done_reason=stop`, no tool calls. Known ollama.com cloud routes are refused; native runtime/model support still needs live evidence. |

Sources checked November 7: [Anthropic structured output](https://platform.claude.com/docs/en/build-with-claude/structured-outputs), [OpenAI Chat Completions reference](https://developers.openai.com/api/reference/resources/chat/subresources/completions/methods/create), [Google's live v1beta REST discovery schema](https://generativelanguage.googleapis.com/$discovery/rest?version=v1beta), [Ollama structured output](https://docs.ollama.com/capabilities/structured-outputs). The Google guide/reference pages redirected to an unavailable documentation surface; the public official discovery schema supplied the generationConfig field evidence. Its documentation does not establish tested service behavior here.

Protocol support is not a claim that every model/version supports the mode or that a remote server honored constrained decoding. An unsupported service can return an error; errors/invalid responses are rejected, without fallback. A server that ignores the mode but happens to return valid output cannot be identified as doing so from that output alone. Quorum lineage, tools and capabilities are not granted by JSON format settings.

## Custody and receipt replay

Ordinary text calls keep their existing v1 receipt shape and legacy response decoders. Structured calls use receipt **v2**, binding raw request/response blobs and a canonical schema blob. `structured_output` contains contract v1, decoder v1, schema digest, a boolean admission result and a static failure code. Unknown versions or changed metadata are rejected.

For structured calls the HTTP exchange is retained before decoding. HTTP-error, malformed, refused, incomplete and schema-invalid responses produce a signed rejected receipt, then raise `StructuredOutputRejected` carrying that event. Undecodable/rejected completion claims are unset, rather than invented; the exact wire response remains available for diagnosis. Known credential echoes still prevent persistence entirely.

The capability budget is reserved once before sending. A rejection consumes that attempt. Unsupported configured adapters fail preflight before spending or network access. A transport exception without an HTTP response remains on the existing spend/error path: no response receipt can be fabricated, and no retry is added. This contribution does not provide general exactly-once external execution or HTTP resource isolation.

Replay re-derives the native request mode/schema from actual stored request bytes, checks the pinned schema and decoder version, re-decodes the raw response, validates its schema/finish/status, then checks the normal completion/usage claims. A v2-to-v1 downgrade is rejected if structured settings remain in the request. Failed receipts cannot verify as successful or back task promotion. Gate schema validation and canonical receipt/output binding remain in force; no gate is relaxed.

`Provider.send()` still returns the decoded result for ordinary text calls; for structured calls `Exchange.result` is `None` until the inference collector has retained and validated the bytes. Use `Inference.run()` for the witnessed/validated path.

## CLI and caller use

`queen infer ... --json-schema schema.json` loads the bounded profile before minting the operator's one-call token. Valid output retains normal exit 0. A received-but-rejected structured result exits 4 and prints the receipt sequence; raw response text is not echoed as a successful answer. Configuration/schema errors remain exceptions and do not initiate inference. No tool runner is introduced.

For worker code, construct the output contract from the signed egg schema, pass it in the inference request, and validate the returned original text before delivery. The gate independently rechecks the egg and receipt. Capsules and oviposition/coordinator integration are subsequent M1 work; this codec change alone does not complete the living-hive exit test.

## Evidence and boundaries

Baseline: 256 offline tests passed with the separately retained historical artifact, one live test deselected, fresh signed test-hive chain verified. Candidate: **306 offline tests passed**, including 50 new tests; ruff and strict mypy passed. Tests cover immutable schemas, native literal wire fields, raw-byte custody, reopen/replay, rejected/error responses, spent budgets/no retry, unsupported mode, production fixture refusal, metadata tampering/downgrade, gate hatch/purge and CLI status.

Offline codec/mocked-HTTP tests do not establish a live vendor/runtime witness. Existing plaintext archive replay remains covered; ordinary CI skips seven archive-dependent cases unless the separately retained ZIP is provided. No raw ZIP, key or private research material is published.

QOS-0008 remains partial overall: streaming and general tool execution are not implemented, and live structured compatibility remains unverified. The owner exception used to merge PR #15 does not apply to this contribution. Existing cross-lineage review requirements, protected branches, frozen v65/A/B/C NO-GO and independent-containment/fresh-session requirements remain unchanged.
