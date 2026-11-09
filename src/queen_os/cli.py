"""`queen` command line."""

from __future__ import annotations

import argparse
import json
import platform
import socket
import sys
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from queen_os.providers.lmstudio import LMStudio

from queen_os import __version__
from queen_os.comb.ledger import ChainBroken
from queen_os.hive import Hive, default_home


def _node_default() -> str:
    name = "".join(c if c.isalnum() or c in "_." else "_" for c in socket.gethostname())
    return (name or "node")[:64]


def cmd_init(args: argparse.Namespace) -> int:
    hive = Hive.init(Path(args.path), args.node_id, args.mode)
    with hive:
        print(f"hive initialized at {hive.root} (node {hive.node_id}, mode {hive.mode})")
        print(f"genesis {hive.ledger.head().hash}")  # type: ignore[union-attr]
    return 0


def cmd_verify(args: argparse.Namespace) -> int:
    with Hive.open(Path(args.path)) as hive:
        try:
            n = hive.ledger.verify_chain(require_signatures=True)
        except ChainBroken as exc:
            print(f"CHAIN BROKEN: {exc}", file=sys.stderr)
            return 2
        head = hive.ledger.head()
        print(f"OK {n} events verified; head seq={head.seq if head else 0} hash={head.hash if head else '-'}")
    return 0


def cmd_tail(args: argparse.Namespace) -> int:
    with Hive.open(Path(args.path)) as hive:
        head = hive.ledger.head()
        start = max(0, (head.seq if head else 0) - args.n)
        for ev in hive.ledger.events(after=start):
            print(
                json.dumps(
                    {
                        "seq": ev.seq,
                        "hlc": ev.hlc,
                        "kind": ev.kind,
                        "actor": ev.actor,
                        "hash": ev.hash[:16],
                        "payload": ev.payload,
                    },
                    ensure_ascii=False,
                )
            )
    return 0


def cmd_providers(_: argparse.Namespace) -> int:
    from queen_os.providers.registry import PRESETS, base_url_for, resolve_credential
    from queen_os.secrets import SecretStore

    store = SecretStore(default_home())
    for name, preset in sorted(PRESETS.items()):
        try:
            cred = resolve_credential(preset, store)
        except PermissionError as exc:
            status = f"ERROR {exc}"
        else:
            if cred is not None:
                status = f"key {cred.fingerprint} ({cred.source})"
            else:
                status = f"no key ({preset.key_env[0]})" if preset.key_required else "no key needed"
        print(f"{name:<11} {preset.kind:<6} {base_url_for(preset):<48} {status}")
    return 0


def cmd_models(args: argparse.Namespace) -> int:
    from queen_os.providers.lmstudio import LMStudio, LocalModelError

    try:
        return _models(args, LMStudio(args.base_url))
    except LocalModelError as exc:
        print(str(exc), file=sys.stderr)
        return 2


def _models(args: argparse.Namespace, manager: LMStudio) -> int:
    if args.models_cmd == "list":
        result: object = manager.models()
    else:
        with Hive.open(Path(args.hive)) as hive:
            result = (
                manager.status(hive, args.operation_id)
                if args.models_cmd == "status"
                else manager.change(
                    hive,
                    args.operation_id,
                    args.models_cmd,
                    args.target,
                    context_length=getattr(args, "context_length", 2048),
                    max_weights_bytes=getattr(args, "max_weights_bytes", 16 * 1024**3),
                )
            )
    print(json.dumps(result, ensure_ascii=False))
    return 0


def cmd_plan(args: argparse.Namespace) -> int:
    from queen_os.queen.oviposition import MAX_PROPOSAL_BYTES, PlanBudget, publish_plan, read_plan, validate_proposal
    from queen_os.serial.afser import sha256_hex

    if args.plan_cmd != "show":
        with Path(args.file).open("rb") as stream:
            raw = stream.read(MAX_PROPOSAL_BYTES + 1)
        budget = PlanBudget(args.calls, args.completion_tokens, args.max_tasks, tuple(args.allow_tool))
        validated = validate_proposal(raw, budget)
        if args.plan_cmd == "validate":
            print(
                json.dumps(
                    {
                        "status": "valid_proposal",
                        "proposal_sha256": sha256_hex(validated.raw),
                        "order": validated.order,
                        "calls": validated.calls,
                        "completion_tokens": validated.completion_tokens,
                        "authority": "none",
                    }
                )
            )
            return 0
    with Hive.open(Path(args.hive)) as hive:
        plan = (
            read_plan(hive, args.goal_id)
            if args.plan_cmd == "show"
            else publish_plan(hive, args.goal_id, raw, budget, objective=args.objective)
        )
        print(
            json.dumps(
                {
                    "goal_id": plan.goal_id,
                    "proposal_sha256": plan.proposal_sha256,
                    "egg_ids": [egg.egg_id for egg in plan.eggs],
                    "event_seq": plan.event_seq,
                    "existing": plan.existing,
                }
            )
        )
    return 0


def cmd_goal(args: argparse.Namespace) -> int:
    from queen_os.queen import planner
    from queen_os.queen.run_budget import RunBudget

    try:
        if args.goal_cmd in {"preview", "plan"}:
            with Path(args.file).open("rb") as stream:
                raw = stream.read(planner.MAX_BRIEF_BYTES + 1)
            objective, notes = planner.brief(raw)
            budget = RunBudget(args.calls, args.completion_tokens, args.max_tasks, args.planner_tokens)
            provider = planner.local_provider(args.base_url)
            request = planner.request_for(args.model, objective, notes, budget)
            wire = provider.encode(request)
            if len(wire.body) > planner.MAX_REQUEST_BYTES:
                raise planner.PlannerError("request byte bound")
            if args.goal_cmd == "preview":
                print(
                    json.dumps(
                        {
                            "request_bytes": len(wire.body),
                            "schema_bytes": len(planner.output_contract().schema_bytes),
                            "budget": budget.to_json(),
                            "worker_calls": budget.max_tasks,
                            "worker_completion_tokens": 512 * budget.max_tasks,
                            "native_token_count": None,
                            "context_fit": "requires_backend_tokenizer_qualification",
                            "authority": "none",
                        }
                    )
                )
                return 0
        with Hive.open(Path(args.hive)) as hive:
            if args.goal_cmd == "plan":
                planner.prepare(hive, args.goal_id, objective, notes, budget, provider, args.model)
                planner.generate(hive, args.goal_id, provider)
                planner.publish(hive, args.goal_id)
            elif args.goal_cmd == "recover":
                planner.accept_receipt(hive, args.goal_id, args.receipt_seq)
            elif args.goal_cmd == "publish":
                planner.publish(hive, args.goal_id)
            print(json.dumps(planner.inspect(hive, args.goal_id)))
        return 0
    except (ValueError, PermissionError) as exc:
        print(
            f"goal operation refused ({type(exc).__name__}); inspect retained ledger evidence before another effect",
            file=sys.stderr,
        )
        return 2


def cmd_work(args: argparse.Namespace) -> int:
    from queen_os.providers.structured import strict_json
    from queen_os.queen import planner
    from queen_os.serial.afser import sha256_hex
    from queen_os.serial.jcs import canonicalize
    from queen_os.workers import execution

    try:
        with Hive.open(Path(args.hive)) as hive:
            if args.work_cmd == "prepare":
                event = execution.prepare_next(hive, args.goal_id, args.worker)
                print(
                    json.dumps(
                        {
                            "prepared_seq": None if event is None else event.seq,
                            "egg_id": None if event is None else event.payload["egg_id"],
                        }
                    )
                )
            elif args.work_cmd == "show":
                print(json.dumps(execution.inspect(hive, args.goal_id)))
            elif args.work_cmd == "preview":
                event, request = execution.preview(hive, args.egg_id)
                run = planner._load(hive, event.payload["goal_id"])
                wire = execution._provider(run).encode(request)
                print(
                    json.dumps(
                        {
                            "request": strict_json(wire.body),
                            "request_sha256": sha256_hex(wire.body),
                            "model": request.model,
                            "max_output_tokens": 512,
                            "context_fit": "requires_backend_tokenizer_qualification",
                            "authority": "none",
                        }
                    )
                )
            else:
                if args.work_cmd == "execute":
                    with Path(args.measurement).open("rb") as stream:
                        raw = stream.read(4097)
                    if len(raw) > 4096:
                        raise execution.ExecutionError("measurement byte bound")
                    proof = strict_json(raw)
                    fit = execution.ContextFit(
                        proof["context_tokens"],
                        proof["prompt_tokens"],
                        proof["schema_tokens"],
                        hive.blobs.put(canonicalize(proof)),
                    )
                    receipt = execution.generate(hive, args.egg_id, args.worker, fit)
                    receipt_seq = receipt.seq
                else:
                    receipt_seq = args.receipt_seq
                decision = execution.recover(hive, args.egg_id, receipt_seq, args.worker)
                print(
                    json.dumps(
                        {
                            "egg_id": decision.egg_id,
                            "verdict": decision.verdict,
                            "evidence_sha256": decision.evidence_sha,
                            "receipt_seq": receipt_seq,
                            "failed": decision.failed,
                            "independent_acceptance": False,
                        }
                    )
                )
        return 0
    except (ValueError, PermissionError, KeyError, TypeError, OSError) as exc:
        print(
            f"worker operation refused ({type(exc).__name__}); inspect ledger/receipts; never retry a spent call",
            file=sys.stderr,
        )
        return 2


def cmd_capsule(args: argparse.Namespace) -> int:
    from queen_os.comb.capsule import MAX_CAPSULE_BYTES, build_capsule, verify_capsule

    with Hive.open(Path(args.hive)) as hive:
        if args.capsule_cmd == "build":
            capsule = build_capsule(hive, args.egg_id, args.max_bytes)
            sys.stdout.buffer.write(capsule.raw + b"\n")  # one UTF-8 framing LF on every OS
        else:
            with Path(args.file).open("rb") as stream:
                raw = stream.read(MAX_CAPSULE_BYTES + 2)
            if raw.endswith(b"\n"):
                raw = raw[:-1]  # only the CLI's single framing LF; not arbitrary whitespace
            capsule = verify_capsule(hive, raw, args.max_bytes)
            p = capsule.payload
            print(
                json.dumps(
                    {
                        "status": "verified",
                        "capsule_sha256": capsule.sha256,
                        "egg_id": p["task"]["egg_id"],
                        "state": p["task"]["state"],
                        "head": p["head"],
                    }
                )
            )
    return 0


def cmd_infer(args: argparse.Namespace) -> int:
    from queen_os.providers import InferenceRequest, JsonSchemaOutput, Message, build
    from queen_os.providers.receipt import Inference, StructuredOutputRejected
    from queen_os.providers.structured import SCHEMA_LIMIT, strict_json
    from queen_os.secrets import SecretStore

    output = None
    if args.json_schema:
        with Path(args.json_schema).open("rb") as stream:
            raw_schema = stream.read(SCHEMA_LIMIT + 1)
        if len(raw_schema) > SCHEMA_LIMIT:
            raise ValueError("JSON schema exceeds the 16 KiB input limit")
        output = JsonSchemaOutput(strict_json(raw_schema))
    provider = build(args.provider, SecretStore(default_home()), args.base_url)
    request = InferenceRequest(
        args.model, (Message("user", args.prompt),), args.system, args.max_tokens, args.temperature, output
    )
    provider.validate_request(request)
    from queen_os.authority import Grant

    with Hive.open(Path(args.hive)) as hive:
        # The operator at the CLI is the authority. It mints a one-call token scoped to exactly this request.
        grant = Grant(providers=(args.provider,), models=(args.model,), max_output_tokens=args.max_tokens, max_calls=1)
        cap = hive.authority().issue("operator:cli", "cli:infer", grant, ttl_ms=10 * 60_000)
        try:
            witnessed = Inference(hive).run(provider, request, actor="operator:cli", capability=cap)
        except StructuredOutputRejected as exc:
            print(str(exc), file=sys.stderr)
            return 4
    print(witnessed.result.text)
    r = witnessed.receipt
    print(
        f"\n[receipt seq={r.seq} hash={r.hash[:16]} lineage={r.payload['lineage']} "
        f"latency={r.payload['latency_ms']}ms tokens={r.payload['input_tokens']}/{r.payload['output_tokens']}]",
        file=sys.stderr,
    )
    return 0


def cmd_secrets(args: argparse.Namespace) -> int:
    import getpass

    from queen_os.secrets import SecretStore

    store = SecretStore(default_home())
    if args.action == "set":
        value = getpass.getpass(f"{args.name} (input hidden): ").strip()
        if not value:
            print("empty value; nothing stored", file=sys.stderr)
            return 1
        print(f"stored {args.name} in {store.set(args.name, value)}")
    elif args.action == "delete":
        store.delete(args.name)
        print(f"deleted {args.name}")
    else:
        for name in store.names():
            secret = store.get(name)
            print(f"{name} {secret.fingerprint if secret else '-'}")
    return 0


def cmd_host_probe(args: argparse.Namespace) -> int:
    from queen_os.host.probe import probe

    report = probe()
    if args.hive:
        with Hive.open(Path(args.hive)) as hive:
            ev = hive.ledger.append("host.probe", f"host:{hive.node_id}", report)
        print(f"host.probe recorded: seq={ev.seq} hash={ev.hash[:16]} signer={ev.signer}", file=sys.stderr)
    for name, sensor in report["sensors"].items():
        detail = sensor.get("value") if sensor["status"] == "OK" else sensor.get("reason")
        print(f"{name:<10} {sensor['status']:<12} {json.dumps(detail, sort_keys=True)}")
    print(f"clock_discipline={report['clock_discipline']}")
    return 0


def cmd_eggs(args: argparse.Namespace) -> int:
    from queen_os.comb.projection import fold_eggs, ready

    with Hive.open(Path(args.hive)) as hive:
        eggs = fold_eggs(hive.ledger)
        ready_ids = {e.egg_id for e in ready(eggs)}
        for e in sorted(eggs.values(), key=lambda v: v.laid_seq):
            flag = "ready" if e.egg_id in ready_ids else ""
            detail = f"stimulus={e.stimulus:.2f} goal={e.goal_id} parents={len(e.parents)}"
            print(f"{e.egg_id}  {e.state:<9} {flag:<5} {detail}")
    return 0


def cmd_gate_review(args: argparse.Namespace) -> int:
    from queen_os.gate.gate import Gate

    with Hive.open(Path(args.hive)) as hive:
        d = Gate(hive).review(args.egg_id)
    print(
        json.dumps(
            {"egg_id": d.egg_id, "evidence_sha": d.evidence_sha, "failed": list(d.failed), "verdict": d.verdict},
            indent=2,
        )
    )
    return 0 if d.verdict == "hatched" else 3


def cmd_info(_: argparse.Namespace) -> int:
    print(
        json.dumps(
            {
                "queen_os": __version__,
                "python": platform.python_version(),
                "os": sys.platform,
                "machine": platform.machine(),
                "home": str(default_home()),
            },
            indent=2,
        )
    )
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="queen", description="Queen-OS multi-agent harness")
    p.add_argument("--version", action="version", version=f"queen-os {__version__}")
    sub = p.add_subparsers(dest="cmd", required=True)

    i = sub.add_parser("init", help="create a new hive")
    i.add_argument("path", nargs="?", default=str(default_home()))
    i.add_argument("--node-id", default=_node_default())
    i.add_argument("--mode", choices=["production", "test"], default="production")
    i.set_defaults(func=cmd_init)

    led = sub.add_parser("ledger", help="inspect the comb ledger")
    lsub = led.add_subparsers(dest="ledger_cmd", required=True)
    v = lsub.add_parser("verify", help="re-derive and check the full hash chain")
    v.add_argument("path", nargs="?", default=str(default_home()))
    v.set_defaults(func=cmd_verify)
    t = lsub.add_parser("tail", help="print the last N events")
    t.add_argument("path", nargs="?", default=str(default_home()))
    t.add_argument("-n", type=int, default=20)
    t.set_defaults(func=cmd_tail)

    sub.add_parser("info", help="environment report").set_defaults(func=cmd_info)
    eg = sub.add_parser("eggs", help="list task eggs and their lifecycle state (ledger fold)")
    eg.add_argument("--hive", default=str(default_home()))
    eg.set_defaults(func=cmd_eggs)

    gate = sub.add_parser("gate", help="verification gate")
    gsub = gate.add_subparsers(dest="gate_cmd", required=True)
    gr = gsub.add_parser("review", help="verify a delivered egg: hatch, purge (oophagy) or hold")
    gr.add_argument("egg_id")
    gr.add_argument("--hive", default=str(default_home()))
    gr.set_defaults(func=cmd_gate_review)

    host = sub.add_parser("host", help="host hardware providers")
    hsub = host.add_subparsers(dest="host_cmd", required=True)
    hp = hsub.add_parser("probe", help="honest hardware probe; with --hive, records a signed host.probe event")
    hp.add_argument("--hive")
    hp.set_defaults(func=cmd_host_probe)

    planning = sub.add_parser("plan", help="validate or explicitly publish a bounded task graph; never infer")
    psub = planning.add_subparsers(dest="plan_cmd", required=True)
    for name in ["validate", "publish", "show"]:
        command = psub.add_parser(name)
        if name != "validate":
            command.add_argument("goal_id")
            command.add_argument("--hive", default=str(default_home()))
        if name != "show":
            command.add_argument("file")
            command.add_argument("--calls", type=int, required=True)
            command.add_argument("--completion-tokens", type=int, required=True)
            command.add_argument("--max-tasks", type=int, default=16)
            command.add_argument("--allow-tool", action="append", default=[])
        if name == "publish":
            command.add_argument("--objective", required=True)
        command.set_defaults(func=cmd_plan)

    goal = sub.add_parser("goal", help="bounded local item-note planning; never execute workers")
    gsub = goal.add_subparsers(dest="goal_cmd", required=True)
    for name in ["preview", "plan", "show", "recover", "publish"]:
        command = gsub.add_parser(name)
        if name != "preview":
            command.add_argument("goal_id")
            command.add_argument("--hive", default=str(default_home()))
        if name in {"preview", "plan"}:
            command.add_argument("file")
            command.add_argument("--model", required=True)
            command.add_argument("--base-url", default="http://127.0.0.1:1234/v1")
            command.add_argument("--calls", type=int, default=4)
            command.add_argument("--completion-tokens", type=int, default=2560)
            command.add_argument("--max-tasks", type=int, default=3)
            command.add_argument("--planner-tokens", type=int, default=1024)
        if name == "recover":
            command.add_argument("--receipt-seq", type=int, required=True)
        command.set_defaults(func=cmd_goal)

    work = sub.add_parser("work", help="explicit bounded item workers for a published local-planner goal")
    wsub = work.add_subparsers(dest="work_cmd", required=True)
    for name in ["prepare", "show", "preview", "execute", "recover"]:
        command = wsub.add_parser(name)
        command.add_argument("--hive", required=True)
        if name in {"prepare", "show"}:
            command.add_argument("--goal-id", required=True)
        else:
            command.add_argument("--egg-id", required=True)
        if name in {"prepare", "execute", "recover"}:
            command.add_argument("--worker", required=True)
        if name == "execute":
            command.add_argument("--measurement", required=True, help="retained backend tokenizer measurement JSON")
        if name == "recover":
            command.add_argument("--receipt-seq", required=True, type=int)
        command.set_defaults(func=cmd_work)

    capsule = sub.add_parser("capsule", help="build or verify bounded task context without executing work")
    csub = capsule.add_subparsers(dest="capsule_cmd", required=True)
    for name in ["build", "verify"]:
        command = csub.add_parser(name)
        command.add_argument("egg_id" if name == "build" else "file")
        command.add_argument("--hive", default=str(default_home()))
        command.add_argument("--max-bytes", type=int, default=32768)
        command.set_defaults(func=cmd_capsule)

    sub.add_parser("providers", help="list model providers and credential status").set_defaults(func=cmd_providers)

    models = sub.add_parser("models", help="explicit LM Studio model lifecycle; never generate or download")
    msub = models.add_subparsers(dest="models_cmd", required=True)
    for name in ["list", "load", "unload", "status"]:
        command = msub.add_parser(name)
        command.add_argument("--base-url", default="http://127.0.0.1:1234")
        if name != "list":
            command.add_argument("--hive", default=str(default_home()))
            command.add_argument("--operation-id", required=True)
        if name in {"load", "unload"}:
            command.add_argument("target", help="exact installed model key or loaded instance ID")
        if name == "load":
            command.add_argument("--context-length", type=int, default=2048)
            command.add_argument("--max-weights-bytes", type=int, default=16 * 1024**3)
        command.set_defaults(func=cmd_models)

    inf = sub.add_parser("infer", help="run one witnessed inference (receipt goes to the ledger)")
    inf.add_argument("provider")
    inf.add_argument("model")
    inf.add_argument("prompt")
    inf.add_argument("--hive", default=str(default_home()))
    inf.add_argument("--system")
    inf.add_argument("--json-schema", help="strict portable JSON schema file (16 KiB max); no repair/retry")
    inf.add_argument("--max-tokens", type=int, default=512)
    inf.add_argument("--temperature", type=float)
    inf.add_argument("--base-url")
    inf.set_defaults(func=cmd_infer)

    sec = sub.add_parser("secrets", help="manage API keys (OS keyring or owner-only file; never argv)")
    sec.add_argument("action", choices=["set", "delete", "list"])
    sec.add_argument("name", nargs="?")
    sec.set_defaults(func=cmd_secrets)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
