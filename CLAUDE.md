# Queen-OS — instructions for any Claude (or human) working here

## On wake, in this order
1. Read `HANDOFF.md`, which holds current state, what's next and open questions.
2. Read the last entry of `LEDGER.md`.
3. Read `docs/BUILD_MAP.md` before adding any module. Every module must trace to a row there.
4. Run `pytest` and `queen init <tmp> && queen ledger verify <tmp>` before changing anything.

## Before you stop
- Append a `LEDGER.md` entry (date, what changed, evidence, decisions, open defects).
- Rewrite `HANDOFF.md` so a cold reader can continue.
- Update the build map row status for anything you built.

## Laws (from the V1 audit, AF-REMEDY-V1 Ch.1). Red Team checks these first.
1. **Witnessed, not declared.** A feature is "built" only with a test that runs it in CI on
   Windows, macOS and Linux. No mocks that share a schema with real execution unless they are
   tagged `fixture` *inside* the signed record.
2. **The ledger is the only coordination channel.** Agents never message each other directly.
3. **Authority never comes from model text.** It comes only from signed capability tokens issued by the host.
4. **Verifiers must be decorrelated** (distinct provider lineages), and deterministic checks run first.
5. **Fail closed.** Ambiguous encodings, stale fences, digest drift and unknown signers all raise.
6. **Cross-platform:** use `pathlib`, `os.replace`, and no POSIX-only calls outside `host/` providers
   that probe and report `UNAVAILABLE`.
7. **Tier honesty:** T3/T4 concepts in the build map are never presented as working.

## Conventions
- Python ≥ 3.12, `ruff` (line 120), `mypy --strict`, `pytest` + `hypothesis`.
- Every security boundary gets a two-arm test: the adversarial arm must fail closed.
- Hermes Agent (MIT) is the reference for the model/tool/skill edge. Ported code keeps its notice in `NOTICE`.
- Commits end with the session attribution lines. Work goes on branches and lands on `main` through PRs.
