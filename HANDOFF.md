# HANDOFF → next engineer on Queen-OS

_Updated November 7, 2026 by Sage/Codex. The owner reports Claude temporarily unavailable, assigns Sage construction leadership, and confirms no known unpublished QOS-0008 work. Continue from main; preserve Claude's branches and attribution._

## Main and this candidate

- Base: `349cbfb31734e26135bc00eb97ff71d3135b593b`, merged #14 documentation. #12 gate and #13 system-prompt correction are on main. No other PR was open at preparation.
- GitHub reports current-main CI 42421568374 and canary 42421568372 successful (push, attempt 1, exact base). Job/step summaries were inspected; these new raw artifacts were not replayed.
- This branch proposes **QOS-0032**: strict JSON receipt/output binding. Python equality let recorded `true` become delivered `1`, including nested values, and JSON decoding collapsed duplicate keys. The gate now rejects ambiguous/nonfinite JSON, validates the recorded response against the egg schema and compares canonical bytes. Numeric 1/1.0 equivalence and key-order/whitespace differences remain valid.
- Candidate until reviewed/merged. Producer evidence: baseline 237 passed; ten new attack cases failed before the fix; final 256 passed, one live deselected. Ruff and strict mypy passed. Final signed-head CI must be observed separately.

## Next construction work

1. Review/land QOS-0032 with final-head CI evidence before relying on receipt-bound structured output.
2. **QOS-0008 structured output**, Sage-led: explicit supported-provider/schema request contract, retained exact bytes and versioned receipt replay. Unsupported/malformed/truncated/refused responses fail visibly. No output repair or hidden model retries. Streaming and general tool execution remain separate.
3. **Resume capsule**: bounded representation bound to verified ledger head, egg and parent digests, with stale/missing/tampered/reopen tests. Bound dependency expansion and bytes explicitly.
4. **Oviposition/coordinator**: bounded untrusted goal-to-DAG proposals, validated before signed publication. Models cannot mint capabilities. Test graph, budget and interruption failures offline.
5. **M1 exit test**: concrete authorized workflow/revision/provider/call/token limits, then decomposition → workers → gate promotion/purge → verified ledger and replayable evidence. This handoff is not a dispatch grant.

Read `CLAUDE.md`, engineering protocol, issues, latest appended ledger and build map; run the offline baseline/fresh-hive chain check before source changes.

## Review and execution limits

Construction/offline testing can continue without Claude. Signed commits, owner-controlled merges and existing cross-lineage review requirements remain unchanged. Self-review/CI are producer evidence, not another lineage or independent containment acceptance. Keep the review gap explicit; prepare concrete diffs/evidence before any owner decision.

Repository enclaves do not contain a hostile local process (QOS-0006). Code-egg checks remain incomplete (QOS-0029); quorum-demanding eggs stay HELD until M2 (QOS-0028). No arbitrary generated-code/shell execution is enabled. The separate hourly remains read-only.

## Smoke chronology and corrections

- Historical 42373449340 CLI answered `Mosquito.`: path verified, explicit bee oracle failed. Preserve the wrong answer.
- Main e59 run 42407907623's externally hash-matched artifact replayed offline: path VERIFIED and `ARCHIVED_SMOKE_PASS` for bee. Failed-answer retention was witnessed in 42386170198. These are dated producer observations, not independent acceptance.
- Run 42380605862 was a feature-branch workflow_dispatch and failed in the earlier combined CLI step. T=0 does not guarantee a correct echo. Keep path integrity and answer quality distinct without relabeling failures or weakening promotion.
- Frozen Astra v65 remains unchanged and NO-GO for A/B/C comparisons: independent acceptance and fresh-session adapter absent. Repository engineering does not inherit or mutate that boundary.

Agent: Sage (Codex)
Codex-Session: 01a1ab22-a4f2-7852-b510-5973fd1a4952
