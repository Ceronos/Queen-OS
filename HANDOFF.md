# HANDOFF → next engineer on Queen-OS

Updated November 8, 2026 by Sage/Codex, leading construction while Claude is unavailable.
Keep owner merge exceptions PR-specific and preserve Claude's work/attribution.

## Verified main

Main is Verified signed **fe95a0fe8401090d3909026f84739993da65f319** (#21), tree
**0089ac30495f853635ae7986b3a325bfcde55936**. Main CI 42499921886 passes all 13 jobs.
Normal main canary 42499921790, attempt 1, job 128790235107 passes all phases: committed
archive pin verified on attempt 1, private extraction/runtime readiness, model acquisition,
pytest/CLI inference, signed-artifact integrity and strict bee oracle. This observes the new
archive path for this exact main revision; it is not broad semantic or containment acceptance.

#16 structured output; #17 one-use Sol code/test clock; #18 bounded capsule; #19 absolute lease
deadline; #20 bounded goal/task admission/publication; #21 canary download hardening are landed.
Each owner review exception covered its PR only. Historical clock-drift and pre-inference
HTTP504 failures remain evidence; later green does not relabel them.

## Current candidate: LM Studio lifecycle and schema route (QOS-0040)

The owner prioritizes LM Studio and explicitly permits manual launch/use of LM Studio or Hermes.
This contribution focuses on LM Studio. The first requested local witness is bounded to a
2048-token context, one synthetic generation, <=512 output tokens and no tools/retries.
Private model inventory and runtime receipts stay outside the public repository. No hosted
API fallback is added; the Sol key is absent and Sol work is deferred.

Existing lmstudio adapter already routes witnessed text. New providers/lmstudio.py +
queen models list/load/unload/status add explicit operator control over an existing local
server, with loopback-only/no-proxy/no-redirect transport, bounded metadata, exact available
LLM/instance selection and context/reported-weight ceilings. A signed intent precedes one
load/unload POST. Repeated operation IDs refuse another POST; GET-only status handles lost
replies without inventing effects. Producer readback establishes current state, not causality
or independent acceptance. Different IDs/hives/clients are not fenced by this slice.

LM Studio-only native JSON-schema preset is enabled from its documented wire contract.
No schema downgrade or repair; exact raw request/response custody, signature verification,
capability spend and separate semantic judgement remain. Other generic presets stay unqualified.
No automatic model download, service install, worker lifecycle tool, hosted fallback or private
Queen-owned engine is implemented. A later pinned local engine supervisor can follow the same
contract; Hermes is architectural reference, not an implementation imported here.

46 new offline cases; full local **518 passed / 9 skipped** (7 absent historical archives,
2 local credential-home restrictions). Ruff/format and strict mypy38 pass. Fresh signed hive
and baseline 472/9 verified before edits. CI and actual local witness results must bind the
exact PR revision; neither is substituted by this preparation note. See LOCAL_MODELS.md.

## Next actions and standing limits

1. Qualify this candidate's offline matrix at exact head/base; keep private runtime receipts
   separate and report actual local witness success, failure or UNKNOWN without retry.
2. Obtain a new PR-specific owner merge decision while Claude is unavailable. #21 approval
   does not cover this candidate. Preserve protected signed squash and verify the signature.
3. Wire a strategic proposal producer through witnessed providers, then prepare the real M1
   goal/worker/gate exit experiment. A canned schema witness or fixture DAG is not that exit.
4. Keep model identity/configuration, protocol/schema validity, task budgets and semantic goal
   quality separate. Weight bytes are not peak VRAM; backend resource placement is not attested.

The separate Sol approval was ONE request / 1024 total completion tokens / USD0.05 / no tools
or retries at bb99eac, expiry 2026-11-10 00:00 UTC. No key or dispatch occurred here. A fresh
exact revision decision is required before any future launch; do not silently extend expiry
or consume the slot checking key presence. Manual LM Studio permission does not broaden SO-0001.

Read CLAUDE.md, docs/ENGINEERS.md, latest LEDGER/BUILD_MAP; baseline and fresh signed hive
before changes. LEDGER append-only. Frozen Astra v65 remains untouched/NO-GO: independent
containment acceptance and a fresh-session adapter remain absent. Manual local repository
work and its owner grant do not migrate that acceptance boundary. Hourly stays read-only.

Agent: Sage (Codex)
Codex-Session: 01a1ab22-a4f2-7852-b510-5973fd1a4952
