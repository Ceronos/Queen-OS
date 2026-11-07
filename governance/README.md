# Governance records

Owner decisions that change what the harness or its engineers may do. Each record is in the repo, so
it is versioned, reviewable, and bound to a commit. The live-inference gate reads the record **at the exact
approved `main` commit**, so editing a record on a branch grants nothing.

| Record | Status | Effect |
|---|---|---|
| `live_standing_order.json` (SO-0001) | active | Claude and Sage may dispatch `live-inference.yml` without a per-run human approval, within the listed providers/models, ≤128 output tokens, ≤20 runs per UTC day. Resolves QOS-0003. |

To revoke SO-0001, set `"status": "revoked"` on `main`. The next dispatch then falls back to Sage's
reviewer-approval mode.
