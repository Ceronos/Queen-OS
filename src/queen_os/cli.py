"""`queen` command line."""

from __future__ import annotations

import argparse
import json
import platform
import socket
import sys
from pathlib import Path

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
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
