# One-use GPT-6.1 Sol structured-output witness (candidate)

Prepared November 7, 2026 (America/New_York). This is a reviewable test package, not a report of model execution or an active standing-order expansion. Merge and live dispatch require the owner's separate approval of this exact candidate and allowance.

## Proposed run

One owner-initiated workflow_dispatch of bounded-sol-smoke.yml on an explicitly approved main SHA, before 2026-11-10 00:00 UTC. Both billable-call and USD 0.05 allowance inputs default false and must be explicitly confirmed. Exactly one inference attempt, gpt-6.1-sol at the official OpenAI Chat Completions endpoint; low reasoning, Standard/default service tier, no temperature, tools, sessions, URL overrides, fallback or retry. max_completion_tokens=1024 covers the endpoint's completion budget, including reasoning. The fixed synthetic wire request must be at most 1024 canonical bytes; it asks for {"answer":"QOS-CANARY-OK"} under a tiny closed required-field schema. No local/Drive/research content enters the request.

At published Standard prices ($2 per million input and $10 per million output tokens), a tiny fixed request with this completion cap should be below $0.02. The $0.05 is an owner authorization ceiling, not an independently enforced provider billing limit or a promise of account eligibility. Reported input/output usage must be present and within 2048/1024 for success. A post-response usage check cannot undo spending. Missing credentials, provider errors, model unavailability or truncation do not authorize a retry, a larger cap or a substitute model.

## Admission and evidence

The workflow has no push, PR or schedule trigger. It requires the exact main SHA, owner account Ceronos, first run attempt, existing live-inference environment metadata and a complete lifetime workflow-run listing. The earliest workflow run is the only eligible slot: prior failed/cancelled runs consume it, and reruns are refused. Future queued runs do not steal the first slot. Workflow-level concurrency serializes runs. The gate rechecks metadata after any environment approval, before reading the configured OpenAI secret. Existing environment protections remain effective and are not changed; inaccessible metadata stops the run. A self-review restriction may need another eligible human; it is not removed here. No secret value is inspected during preparation. The environment's name does not by itself establish which secret scope supplied a value.

The generic workflow and SO-0001 are unchanged; Sol is not added to their recurring allowances. One-use accounting trusts GitHub's retained run history and the owner: history deletion or an administrator replacing the workflow can invalidate it. This is not exactly-once execution against a hostile administrator or external service.

The model receives one host-issued capability scoped to openai/gpt-6.1-sol, one call, 1024 completion tokens and no tools. Received structured rejection retains its signed v2 receipt/raw bytes and fails. Transport failure retains the spent ledger without inventing a response receipt. The export contains only hive.json, closed SQLite ledger, content-addressed blobs and a result summary; never the vault, private key or environment. Offline replay checks the signed chain, capability signature/scope/order, exact fixed wire request, provider classification, receipt and usage. Embedded signatures establish attribution, not independent provider authentication.

Schema/path validity and the exact answer comparison are separate signals. A schema-valid wrong answer remains semantic_match=false and is not relabelled a semantic pass. The job's success only establishes a verified bounded path and schema; inspect the semantic field separately. Rejection, missing/over-limit usage or transport failure makes the live job red. Evidence upload runs after success/failure; no evidence directory is fabricated when admission or missing credentials prevented the attempt.

## Preparation and limits

All preparation uses signed fixture-marked test hives and mocked HTTP. Offline controls cover context/consent/expiry/history refusal, cancellation, fixed request fields, one attempt, invalid output/raw custody, wrong-answer separation, missing/excess usage, production fixture refusal and credential-free export/replay. No real-model request or live key access has occurred. Cross-platform CI and owner review remain pending until recorded in the PR.

The initial source is signed main a6dc117b12479959ed50e0a92df8602628fb5eb5, which landed #16 with the tested tree; its CI 42429769412 and keyless canary 42429769335 passed. Frozen v65, its NO-GO and independent-containment/fresh-session requirements are unchanged. This request is not an M1 exit experiment, memory comparison or independent review.

## Launch/readback

After reviewing the PR and current CI, the owner can authorize its signed squash and the single request/allowance. Then use Actions → one-use bounded Sol smoke → Run workflow, main, exact signed merge SHA, and both confirmations true. The connected tools currently expose no workflow-dispatch action; local GitHub CLI is signed out. Do not copy tokens or bypass that limitation. An owner launch may be needed. A configured OPENAI_API_KEY and account model access are unverified; no credential setup or environment edit is part of preparation.

After completion, bind the run/attempt to the exact main SHA, fetch the artifact's external GitHub digest, download and hash it, and replay in an isolated extraction without private keys or a model call. Workflow/producer replay is not independent acceptance. Do not rerun a failure; diagnose the retained evidence and propose a new reviewed test version if needed.

Sources checked: https://developers.openai.com/api/docs/models/gpt-6.1-sol and https://developers.openai.com/api/docs/guides/latest-model?model=gpt-6.1-sol . API docs establish advertised interface/pricing, not this account's access or live behavior.
