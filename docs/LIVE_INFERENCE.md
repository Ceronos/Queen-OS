# Offline checks and separately authorized live inference

Pull requests and pushes to `main` run offline tests, lint, types and the
non-inference CLI smoke. Pushes to `main` also run the keyless local-model canary
(`live-canary.yml`, see `LIVE_CANARY.md`), which uses no secrets and has no PR trigger. They do not install Ollama, pull models, map provider
keys into test steps or invoke `queen infer`. The test command explicitly excludes
`tests/live` as well as requiring the non-live marker.

Live inference is a separate `workflow_dispatch` workflow. Nothing in this change
dispatches it or configures repository secrets/environments. It is ineligible on
feature branches and cannot start through a push, PR, schedule or workflow-run
trigger. It requires:

1. An explicit confirmation and exact approved 40-character `main` commit SHA.
2. An authorization-record URL covering actual scope, accepted prerequisites,
   provider/model, one request, output-token limit and any monetary allowance.
3. An explicitly named provider/model and 1–128 output tokens. There are no
   implicit hosted model defaults and no extra live pytest/CLI inference calls.
4. An **existing** `live-inference` GitHub environment with required reviewers and
   prevention of self-review. Metadata failure, absence or missing rules stops
   preflight before any provider setup. The live job references that environment
   and rechecks its metadata after approval.

Configure reviewers and disallow administrator bypass in repository settings before
requesting a live run. Prefer environment-scoped API secrets. No new reviewers,
keys, environments or approval records are supplied by this PR. A missing key
fails the explicitly selected hosted call; it is not silently replaced by a
fixture or a different provider.

The checker verifies dispatch metadata and reviewer configuration. It does **not**
authenticate or fetch the authorization record, prove that its content is true,
prove independent containment acceptance or enforce a provider's exact billing.
The required reviewer must check those prerequisites and the selected commit
before approval. Repository administrators remain in the trust boundary. A manual
confirmation or environment label alone is not security acceptance. Existing
research NO-GO decisions are not cleared by this workflow.

The optional Ollama installer retains its upstream installation mechanism; runtime
and installer pinning are separate unfinished work. This PR does not claim actual
model execution, process containment, external-provider cancellation or spending
verification. Its local tests use synthetic GitHub metadata only.

References: [environment protection and access to secrets](https://docs.github.com/en/actions/how-tos/deploy/configure-and-manage-deployments/manage-environments),
[environment metadata API](https://docs.github.com/en/rest/deployments/environments#get-an-environment).

## Standing-order mode (added by Claude, owner order SO-0001)

Besides the reviewer mode above, `authorization_ref = standing-order:SO-0001` with `engineer = claude|sage`
admits a dispatch without a per-run human approval. The order is read from
`governance/live_standing_order.json` at the approved main commit. The gate enforces its provider/model
scope, ≤128 output tokens and a per-UTC-day run budget counted from the Actions API, and fails closed
when the count cannot be established. An environment that requires self-review prevention is refused in
this mode with an explicit message, because dispatches through the owner's account would otherwise hang
forever waiting for an approval that can't be given.
