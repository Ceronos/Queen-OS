# Engineering protocol: Claude + Sage on one hive

Two engineers from **different model lineages** work on Queen-OS: Claude (Anthropic) and Sage
(OpenAI / Codex). That fact is part of the architecture. Cross-review between us is the
Tri-Sovereign decorrelation rule (AF-REMEDY-V1 §1.4) applied to our own code.

## Lanes (who leads what; either may contribute anywhere through a PR)

| Lane | Lead | Scope |
|---|---|---|
| Substrate & cognition | Claude | ledger, eggs, authority, providers, workers, gate, queen |
| Admission, recovery & hardware | Sage | CI/live-run authorization, recovery/interruption contracts, Thelio Astra hardware runs, containment evidence |
| Architecture decisions | Owner (Ceronos) | `owner-decision` items in `docs/ISSUES.md` |

## Branches & PRs
- Branch prefixes: `claude/<topic>` and `codex/<topic>`. Never push to another engineer's branch.
- **Branch from `main`.** The first stack landed in #8 (90b4035). Stack on another open PR only when your work
  depends on it, and say so in the PR body. Short stacks merge cleanly. Long stacks need a re-land (see #7 → #8).
- **`main` rules:** PR required, linear history, **signed commits**. Merge with **Squash and merge**. Unsigned
  commits block the merge (QOS-0026).
- GitHub web-editor commits provide a signed contribution path without adding a local key. Preserve agent/session attribution and verify the resulting commit; an API-created commit is not assumed signed. Local CLI signing remains separately configurable.
- Every PR body has: scope, evidence (test counts, CI run IDs), limits, and the issue IDs it opens or closes.
- **Cross-lineage review:** a PR from one engineer gets a review comment from the other before the owner merges.
  Review means reading the diff and running the tests, not summarizing the PR body.

## Shared files (to avoid merge conflicts, QOS-0016)
- `LEDGER.md`: **append only**. Add your entry at the bottom, never edit others' entries.
- `docs/ISSUES.md`: append rows. Change `Status`/`Owner` only for issues you are fixing or that you raised.
- `HANDOFF.md`: whoever opens the newest PR in the stack rewrites it. Write it for a cold reader, and
  credit the other engineer's open work.
- `docs/BUILD_MAP.md`: change the status cells of rows you built. Propose new rows in the PR body.

## Hardware evidence (Thelio Astra)
Run on the target machine and attach the output to the PR or issue:
```
queen init ./hw-hive --node-id thelio_astra
queen host probe --hive ./hw-hive          # signed host.probe event; sensors report OK / UNAVAILABLE / ERROR
QUEEN_TEST_TMP=/var/tmp/qos pytest -q --ignore=tests/live
queen ledger verify ./hw-hive && queen ledger tail ./hw-hive -n 2
```
A hardware claim (TPM, PTP, NUMA, core pinning, hugepages) counts as evidence only when a signed
`host.probe` event or a test result from the actual machine backs it. Anything else is a plan.

## Live inference
Through `.github/workflows/live-inference.yml` (see `docs/LIVE_INFERENCE.md`), or the separately owner-approved one-use `.github/workflows/bounded-sol-smoke.yml` (see `docs/BOUNDED_SOL_SMOKE.md`). The latter is a candidate until owner approval; it does not extend SO-0001. Keys belong in the
`live-inference` **environment** secrets. They never go in chat, files or commits.
