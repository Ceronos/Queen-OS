# Queen-OS recursive improvement runbook

## Baseline checked November 17, 2026

| Path | Evidence | Next gate |
| --- | --- | --- |
| Queen-OS execution | Signed main `0803ab7fbb0d708bad051d6655dd6554c96fb0ae`. Astra independently passed lint, typing, fresh hive verification and 619 offline tests, with 9 skips. The planner/worker fixture exercises publication, three workers, spend ceilings and the correctness gate. | Complete one new authorized **live** goal and reopen its verified ledger. [Main CI](https://github.com/Ceronos/Queen-OS/actions/runs/42599086097) |
| Inference and evidence | The hosted keyless canary at the same main commit passed. Astra independently replayed its exported archive, verified five signed events and accepted the strict answer. Archive SHA-256 `80684409d35bb26944976d07163b1d09d07cc78a773389b936d19a6c261f3d7e`. | Qualify the exact local model, route and structured worker request on Astra. The configured loopback service was unreachable in this pass. [Main canary](https://github.com/Ceronos/Queen-OS/actions/runs/42599086099) |
| Operational feedback | The real planner published a goal. One real worker passed the oracle. A second used its whole 512-token completion budget, returned empty content and was recorded as rejected. Its dependent task stayed blocked. | Resolve [QOS-0043](ISSUES.md#qos-0043-reasoning-policy-qualification) for a fresh goal. Preserve the spent attempt and its evidence. |
| Astra delivery and engines | Host-side dry-run observed. The reply on the bridge issue, signed host attestation and the full scheduled capability audit are pending. | Verify the bounded return receipt and the saved cloud scheduler settings. Keep discretionary and private work independent of repo integration. [Integration evidence](https://github.com/Ceronos/Queen-OS/issues/26#issuecomment-6944337529) · [Probe](https://github.com/Ceronos/Queen-OS/issues/32) |
| Architecture and policy | Branch/CI evidence supports isolated changes. No controlled two-generation policy result has been established. | Define a static control, exact versions, a scoring rule and a stopping rule before running the policy pilot below. |
| Model weights | RSI-001 defines two trained generations. The training runtime, data split, comparison and promotion evidence remain pending. | Preregister a candidate recipe and independent evaluation. [RSI-001](https://github.com/Ceronos/Queen-OS/issues/30) |

The archived canary demonstrates a bounded live transport and strict answer check in CI. The replay
was offline on Astra. The frozen v65 containment study has its own independent review and real-agent
NO-GO. Repository development and read-only experiment preparation can proceed under their existing scope.

## Complete a live Queen-OS goal

1. Read the old goal and its signed terminal evidence. Preserve successful artifacts, the spent
   rejection and the blocked dependency. Use the existing readback and recovery rules for known
   receipts and uncertain effects. [Worker contract](../BOUNDED_WORKERS.md)
2. Read the existing model inventory. Identify the exact installed model instance, server version,
   API route, structured schema, renderer, loaded context and reasoning behavior. Check any explicit
   reasoning control on the actual structured-worker endpoint before treating it as supported.
   LM Studio's documented native chat setting applies to its native route. The current source-bound
   planner and worker path pins the LM Studio-compatible adapter. The Ollama inventory endpoint
   answered on Astra, but choosing it for the same goal requires qualifying and binding that
   provider explicitly in the planner, worker and receipt checks. [Local model controls](LOCAL_MODELS.md) · [Native chat reference](https://lmstudio.ai/docs/developer/rest/chat) · [Compatibility reference](https://lmstudio.ai/docs/developer/openai-compat)
3. For a fresh authorized goal, fix the planner and worker limits and retain the tokenizer
   measurement against each prepared request. Record the goal and request before effects. Follow
   the documented planner, worker, gate and recovery paths. [Planner contract](LOCAL_PLANNER.md) · [Worker contract](../BOUNDED_WORKERS.md)
4. Reopen and verify the signed ledger, receipt chain, exact artifacts and per-task verdicts.
   The live exit evidence is a real planner, real workers, a verified dependent result and replay
   of the terminal state. If the goal stops, retain the cause and spent attempts.

## Run the policy pilot

Pin the repository SHA, local model and tokenizer, baseline instruction, allowed policy
change, scorer, data split, seeds, compute cap, evaluation threshold and regression veto ahead
of time. Give the proposer only its permitted input and the allowed validation feedback. The
holdout remains with the evaluator.

1. Run the baseline and one candidate on the same validation cases. Keep per-case outputs and costs.
2. Apply the predeclared gate. Promote a qualifying candidate only for the experiment.
3. Use that exact accepted policy to make the next proposal. In parallel use the original policy in
   a static arm with the same opportunity and budget. Preserve rejected candidates and the lineage
   of the actual policy used by each proposer.
4. Freeze the selected artifacts and use the final holdout once. Compare performance, regression
   failures, and total cost. Record a tie, no gain or an inconclusive comparison as an outcome.

Architecture changes follow the same comparison discipline. Use isolated branches and run the same
tests and measurement against the pinned baseline and candidate. Preserve the source SHA, CI,
independent reviewer and resulting merge SHA. An authorized maintainer integrates a change after
the required reviews and checks. Deployment has a separate environment receipt.

## Run RSI-001 with model weights

Use the two-generation design in [issue #30](https://github.com/Ceronos/Queen-OS/issues/30).
The training recipe should allow only typed choices over approved data and parameters. A separate
trainer writes the adapter in the approved environment. Retain checkpoint, tokenizer, recipe,
dataset split and adapter digests, budget usage and training logs. An evaluator with separate
holdout custody compares the candidate to its parent and publishes the applicable verdict. A
promoted model stays within the experiment and actually serves as the next proposer.

Before training, record the exact baseline, seeds, time and resource ceilings, evaluation scales
and minimum effect, regression veto, evaluator identity, stop/recovery behavior and rollback
artifact. Run the fixed original proposer as the control in the second generation. To establish a
closed model-weight loop, the record must show G0 proposing the update that produced G1 and the
verified G1 proposing the update that produced G2. Report research effectiveness against the
fixed proposer separately from the model's task score.

Keep the experiment ID, authorized scope, source commit, input and output digests, action intents,
usage, evaluation and verdict together. Feed the result and the next testable hypothesis into the
next research pass. Preserve raw evidence in its approved storage location and link the public,
reviewable summary from the issue or PR.
