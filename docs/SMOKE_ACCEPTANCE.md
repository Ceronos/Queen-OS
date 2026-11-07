# A bounded live smoke milestone, with an explicit answer oracle

The first engineering milestone is narrow: the real provider → capability spend
→ stored request/response → signed receipt/chain path works for a small, keyless
local-model call. This is separate from adversarial containment acceptance and the
frozen v65 two-episode A/B/C study. Repository development is not blocked by that
study's unfulfilled acceptance requirements.

## Evidence already recovered

[Canary run 42373449340](https://github.com/Ceronos/Queen-OS/actions/runs/42373449340)
completed at producer commit `365de353ced5e7d4bf9b21aff5f5575cc1186163` on the
`claude/m1-eggs` branch. It made two calls: a 32-output-token live pytest request
and a separate 16-output-token CLI request. Only the CLI hive was exported.

Artifact `13573899082`, externally recorded SHA-256
`29dab4f7c21d336a36ae35a31547aaaadcf05e8ed28fffd508fd136bed1103e5`,
contains five signed events, a production hive manifest, and the exact request and
response blobs. No private key/vault is present. The original ZIP is retained locally, not published in Git. Public provenance metadata
is in `tests/fixtures/canary-42373449340.json`. Using separately downloaded bytes in
an offline regression test does not constitute another live run.

Actual readback found the CLI answer **`Mosquito.`** to the comb-building question:
four output tokens against a 16-token request and a one-call capability. The live
pytest log separately reports `bee`. The previous tests accepted nonempty text,
so its green result establishes the witnessed call path, not a correct CLI answer.
The wrong answer and original signatures are preserved instead of being rewritten.

The archive also contains the historical `host.probe` PTP overclaim later corrected
by QOS-0024. Hardware/clock claims are not an acceptance criterion for this smoke
milestone and are not validated by the archive checker.

## What this change requires

- Both canary prompts now request the fixed word `bee`; this is a transport and
  instruction-following smoke oracle, not a bee-knowledge benchmark.
- Generation temperature is explicitly zero. Existing call/token limits remain:
  one 32-token pytest call and one 16-token CLI call in separate one-call hives.
- Live pytest rejects a mismatched answer. The CLI's exported raw response is
  independently re-decoded by the offline checker and must also match `bee`.
- A future canary is successful only after the exact candidate's actual live run
  passes. Offline tests and this PR alone do not supply that result.

The existing main/manual workflow triggers and hosted-key policy are unchanged.
No hosted key, repository environment, reviewer rule or standing-order scope is
modified by this change. The installer-script pinning remainder in QOS-0005 stays
open. There is no automatic model-call retry in the answer checker.

## Preserve valid evidence when the CLI answer is wrong

[Run 42380605862, attempt 1](https://github.com/Ceronos/Queen-OS/actions/runs/42380605862)
executed commit `9a907655de0f249f5a4001770a6de88e4bc30ab8`. Live pytest returned
`bee`, but the CLI returned `beeedom` (3 output tokens / 16 allowed). The five-event
signature check passed; the word checker exited 2. The job correctly failed, but
its later artifact upload was skipped, leaving only producer logs for readback.

The workflow now orders its CLI phases as:

1. Verify the candidate ZIP's bounded public layout, signatures, raw bytes and
   one-call scope **without** an answer oracle. Invalid/private/incomplete bundles
   fail here and cannot reach the normally success-gated upload. Pin the verified
   ZIP digest in a step output only after admission succeeds.
2. Upload the admitted evidence directory. Missing files fail the upload.
3. Check the same ZIP against the pinned digest and the unchanged `bee` oracle.
   A mismatch still exits 2 and fails the job; it cannot erase the earlier artifact.

There is no `continue-on-error`, unconditional upload, added inference, changed
prompt or retry. A canceled run, earlier live-pytest failure, structural rejection
or failed artifact upload may still leave no exported CLI evidence. Only the CLI
hive is exported; pytest's separate hive is not. These are explicit limits of this
fix, not evidence that an unavailable bundle passed.

Offline tests exercise the actual verifier CLI with the retained historical
wrong-answer archive: admission succeeds, a local retained copy survives, and the
answer gate still exits 2. A synthetic private-file bundle fails CLI admission.
The local copy is a retention rehearsal, not a GitHub artifact-service test.
The new workflow revision still needs an authorized live run to witness upload
ordering in GitHub. No new model call is required by these offline tests.

## Offline artifact verification

Use a digest from a separately obtained receipt (such as the GitHub artifact API),
not a digest supplied only inside an untrusted archive:

```sh
python scripts/verify_smoke_artifact.py /path/to/downloaded-canary.zip \
  --expected-sha256 29dab4f7c21d336a36ae35a31547aaaadcf05e8ed28fffd508fd136bed1103e5
```

That returns `ARCHIVED_INFERENCE_PATH_VERIFIED`. Add `--expect-word bee` to obtain
`ARCHIVED_SMOKE_ANSWER_MISMATCH` and exit status 2 for this historical fixture.
The checker verifies the archive digest, bounded regular-file layout, production
genesis, event/capability signatures, one issued grant/spend/receipt, provider/model/
subject/token scope and spend timing, raw-byte re-derivation, output limit and the
optional answer oracle. It makes no network/model call and needs no private key.
SQLite initialization runs only on a disposable extraction, never on the original
ZIP. The externally pinned bytes are used directly for extraction.

`ARCHIVED_SMOKE_PASS` means that the reviewed archive also passes the explicitly
requested word oracle. It does not authenticate a model server, prove independence,
establish fresh provider state, exclude covert channels, or authorize an experiment.
The caller still has to establish the archive's run/commit association. Embedded
public keys/signatures establish attribution under that provenance, not truth.

Archive replay tests require `QUEEN_ARCHIVED_SMOKE=/path/to/downloaded-canary.zip`.
Ordinary offline CI does not download the archive or request credentials; seven
archive-dependent cases explicitly skip without that path. They passed locally
against the externally hashed original ZIP. Negative ZIP/digest checks still run
without it, and the authorized live canary validates its own newly generated bundle.
Skipped replay cases are not counted as evidence that the archive was reverified.

## Next acceptance work

1. Run the corrected bounded canary at an explicitly selected commit through the
   authorized workflow and preserve its run/attempt, runtime/model identity, external
   artifact digest and offline verification result. Keep call-path and answer
   outcomes separate.
2. Continue worker/capability/gate implementation using those engineering results.
3. Before the separate A/B/C research trial, agree on a bounded threat profile,
   obtain independent acceptance for the exact containment candidate, and implement
   and verify the fresh-session/credential-broker contract. Do not mutate frozen
   v65 or treat a smoke pass as that acceptance.
