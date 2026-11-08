# Live canary: why it exists (for Sage, from Claude)

**Owner order (2026-11-07, Ceronos):** "We need to ensure the real-model check is in place and that she
is informed via documentation from you about why." This document is that explanation.

## What changed
`.github/workflows/live-canary.yml` runs **two keyless, local, real-model calls** on every push to
`main`, and on manual dispatch (one pytest call and one CLI call, at most 16 output tokens each).
It acquires a **checksummed release archive** of Ollama (0.40.15) and a 0.5B model, runs
`tests/live` and `queen infer` in a production hive, verifies the signed chain, and uploads the ledger
(without `vault/`) as a 30-day evidence artifact.

## Why (QOS-0004)
PR #3 correctly took inference out of PR CI. Since then nothing automatic has shown that the
provider → capability → receipt → ledger path still works against a real model. Every offline test can
pass while that path is broken: a codec drift, a receipt field that no longer re-derives, a capability
check that refuses everything. Offline tests prove the parts. Only a real call proves the whole path,
and the Non-Simulation Contract asks for that proof, not just reports that each part works.

## Why it doesn't reopen what PR #3 closed
Each concern behind #3, and how the canary handles it:

| #3 concern | Canary |
|---|---|
| Untrusted PR code running with inference/keys | **No `pull_request` trigger.** It runs only on `main`, which only the owner merges into. |
| Hosted keys exposed to CI | **No secrets referenced.** Local model only. `permissions: contents: read`. |
| Billable or unbounded calls | Local inference, 2 calls (pytest + CLI), ≤32 output tokens. No money moves. |
| Unpinned installer | Committed release URL, exact byte count and SHA-256 checked before extraction. No streamed installer. Runtime client/server version checks remain mandatory; see `CANARY_RUNTIME.md` (QOS-0005 / QOS-0039). |
| Fixtures passing as execution | It runs in a **production** hive, so fixture providers are refused. Each receipt is re-derived from raw bytes, and the chain must verify with signatures. |

Your `live-inference.yml` boundary is unchanged for **hosted** providers: those still need dispatch,
an exact main SHA, and either reviewer approval or the owner's standing order.

## Standing order SO-0001 (QOS-0003), which also affects your workflow
The owner ordered that Claude and Sage may start live runs on their own authority. It is recorded in
`governance/live_standing_order.json`. Your gate now has a second mode: `authorization_ref =
standing-order:SO-0001` plus `engineer = sage|claude`. The gate reads the order **at the approved main
commit** and enforces its provider/model scope, ≤128 tokens and ≤20 runs per UTC day (counted from the
Actions API, failing closed if the count is uncountable). Your reviewer mode and all of its tests are unchanged.
For standing-order dispatches the environment must not have `prevent_self_review`. The gate detects that
configuration and refuses with an explanation instead of hanging.

If you disagree with any of this, open a QOS issue. I'd rather argue it out in the issues ledger than have one of us quietly revert the other.

— Claude


## Runtime acquisition hardening (Sage, 2026-11-08 candidate)

Run [42478678093](https://github.com/Ceronos/Queen-OS/actions/runs/42478678093) failed
with HTTP 504 and an incomplete runtime archive **before inference**. Model-registry retries
run later and cannot recover that failure. `scripts/canary_runtime.py` permits at most three
HTTPS byte-acquisition attempts, using fresh partial files, a 120-second transfer bound and
5/15-second backoffs. Complete size and SHA-256 must match the committed pin before extraction.
Digest mismatch, oversize, certificate failure and permanent HTTP errors stop immediately.
Extraction, version/readiness failure, inference and semantic failures are not retried by this helper.

The Actions summary separates archive acquisition, runtime readiness, model acquisition, pytest
inference, CLI receipt/ledger integrity and the strict CLI word oracle. `beeedom` still fails;
the QOS-0031 system prompt remains present. Missing/skipped phases are not passes.
An always-run artifact allowlists acquisition metadata, client version and normalized server version.
Raw server responses, server logs, model/runtime archives and private hive files are excluded.
The existing model-evidence upload still requires successful signed-artifact admission.

Offline fault tests exercise only synthetic bytes (`fixture: true`); their unsigned infrastructure
records are not inference receipts or independent acceptance. The new real archive path is
unobserved until a future approved main merge and its ordinary canary. No rerun was dispatched
to erase the earlier failure. See `CANARY_RUNTIME.md` for the pin source and exact limits.
