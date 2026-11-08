# Goal-to-task planning — M1 candidate (QOS-0037)

The host accepts an inert task proposal against a separately supplied objective and resource limits, then signs and publishes the accepted graph. Validation is deterministic; it does not ask a model to approve its own output. This slice does not call a strategic model, run a scheduler, dispatch tools or establish the M1 live exit.

## Contract

The proposal is UTF-8 JSON with exactly `v: 1` and a nonempty `tasks` list. Each task has exactly these fields:

```json
{
  "v": 1,
  "tasks": [
    {
      "id": "answer",
      "ploidy": "diploid",
      "input": {
        "question": "Synthetic fixture question"
      },
      "schema": {
        "type": "object",
        "properties": {
          "answer": {
            "type": "string"
          }
        },
        "required": [
          "answer"
        ],
        "additionalProperties": false
      },
      "tools": [],
      "stimulus": 0.9,
      "parents": []
    }
  ]
}
```

Local IDs are lowercase identifiers, not paths or existing egg IDs. Parents name tasks in the same proposal. Unknown fields, duplicate JSON keys/IDs/parents, dangling/external parents, cycles and unsupported encodings fail closed. Input remains untrusted task data.

Every task uses the existing portable closed-object JsonSchemaOutput contract; remote schema references are unsupported. The existing Bresslau valve derives its execution profile. A proposal cannot downgrade risk by choosing haploid. Tasks requiring the unimplemented M2 quorum are refused at admission.

The host supplies the goal ID, nonempty objective and PlanBudget separately. Those do not come from proposal fields. Tool requests must be a subset of the host's exact allowlist; the default is empty. Admitting a tool name does not implement its dispatcher or execute it.

## Bounds and budget units

| Bound | Limit |
| --- | --- |
| Raw and canonical proposal | 32,768 bytes each |
| Tasks | Host limit, default 16, hard maximum 32 |
| Edges / parents per task / longest path | 128 / 16 / 8 edges |
| Host objective | 8,000 canonical bytes |
| Task input | Existing 8,000 canonical-byte egg bound |
| Output schema | Existing 16 KiB portable schema bound |
| Host call / completion-token limits | Positive exact integers, hard maxima 10,000 / 1,048,576 |

Admission sums the derived profiles, not model estimates. Each task reserves planning capacity for its profile's max_calls × max_output_tokens. Currently diploid is one call × 512 completion tokens; low-risk haploid is three × 1024. The sum must fit the host limits before any publication write.

At spending time, the existing serialized Authority._reserve transaction checks both the capability and the published task/goal limits, then records a signed plan charge before the effect. Separate/replacement capabilities cannot reset a task's lifetime allowance or enlarge its admitted output/tool limits. An unplanned task cannot borrow an existing goal's budget. Missing/inconsistent prior plan charges cause refusal, not a zero-use assumption. Tool attempts count as calls and reserve zero completion tokens.

Completion tokens here mean the requested output ceiling, not measured generation, input tokens, wall time, energy, tool cost or USD. This is not a financial budget engine or a provider-billing guarantee. Failed or uncertain effects consume their reservation; there is no automatic refund or retry. Larger allowances require a separately admitted new goal/decision, not editing a committed plan.

Legacy standalone tasks/capabilities keep their existing behavior. The new shared check applies to tasks under a published goal. Trusted host code can still issue other standalone grants; this is in-process admission/accounting, not process containment.

## Publication and recovery

- validate_proposal is pure. It returns immutable canonical bytes/order/derived totals and grants no authority.
- publish_plan validates all tasks/profiles/budgets first. It maps local IDs deterministically to egg IDs, signs the TaskEgg bodies, and appends every egg plus goal.planned in one SQLite writer transaction. Other readers see the complete graph after commit or none of it.
- The signed plan records the objective and digest, canonical proposal and digest, host limits, derived totals and task/profile mapping. No worker capability or inference is issued by publication.
- One stable host goal ID is the deduplication key. Exact canonical proposal/objective/budget replay returns the existing source-verified publication without new events. A changed plan, objective or policy under that ID conflicts. Existing standalone history cannot be retroactively attached.
- Each new event is fetched/verified after commit. If return/readback fails, publication may already have committed. Use read_plan / plan show to inspect the existing goal before choosing any later effect; do not assume rollback or silently republish.
- Worker readiness, fenced claims, receipt binding and Gate promotion remain controlling after publication. Graph validity/budget fit do not establish that the proposal actually solves the objective.

## CLI

```bash
queen plan validate proposal.json --calls 1 --completion-tokens 512
queen plan publish goal_example proposal.json --objective 'Synthetic fixture goal' \
  --calls 1 --completion-tokens 512 --hive /path/to/hive
queen plan show goal_example --hive /path/to/hive
```

Validation opens no hive. Publish is an explicit operator action using the host signer. Show is recovery readback. No command invokes a provider or auto-executes tasks. The Python equivalents are validate_proposal, publish_plan and read_plan in queen/oviposition.py.

## Producer evidence and exclusions

57 offline cases cover graph/schema/encoding/host-budget rejection without writes; canonical numeric expansion; parent ordering and bounded shared ancestry; atomic rollback/failed commit/other-reader visibility; stable replay/conflict; uncertain postcommit recovery; signed-source corruption; real fixture claim/receipt/Gate/capsule integration; competing capabilities; lifetime task budget, unknown effects and tool intersection. Fixtures are marked inside signed receipts and only used in test hives.

Local full suite: 432 passed, 9 skips (7 absent historical archive checks; 2 credential-home fixtures unavailable locally). Ruff check/format and strict mypy pass. Cross-platform CI must qualify the exact PR revision. No fresh real-model planning result, semantic goal acceptance, cross-lineage review, independent containment acceptance or M1 exit is claimed.

