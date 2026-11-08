"""One fixed structured Sol call; bounded, fixture-testable and replayable without keys."""

from __future__ import annotations

import argparse
import json
import os
import shutil
from dataclasses import replace
from pathlib import Path
from typing import Any

import httpx

from queen_os.authority import Grant
from queen_os.authority.tokens import Capability
from queen_os.comb.blobs import BlobStore
from queen_os.comb.enclaves import Enclaves
from queen_os.comb.hlc import HybridLogicalClock
from queen_os.comb.leases import Leases
from queen_os.comb.ledger import Ledger
from queen_os.crypto.keys import public_from_hex, verify
from queen_os.hive import Hive
from queen_os.providers import InferenceRequest, JsonSchemaOutput, Message
from queen_os.providers.adapters import OpenAICompatibleProvider
from queen_os.providers.base import Provider, ProviderError, WireCall
from queen_os.providers.receipt import Inference, StructuredOutputRejected, verify_receipt
from queen_os.secrets import Secret
from queen_os.serial.jcs import canonicalize

MODEL = "gpt-6.1-sol"
LIMIT = 1024
EXPECTED = "QOS-CANARY-OK"
SCHEMA = {
    "type": "object",
    "properties": {"answer": {"type": "string"}},
    "required": ["answer"],
    "additionalProperties": False,
}
REQUEST = InferenceRequest(
    MODEL,
    (Message("user", 'Return {"answer":"QOS-CANARY-OK"} using the JSON schema.'),),
    max_tokens=LIMIT,
    output=JsonSchemaOutput(SCHEMA),
)


def check_usage(inputs: int | None, outputs: int | None) -> None:
    if type(inputs) is not int or type(outputs) is not int or not 0 < inputs <= 2048 or not 0 < outputs <= LIMIT:
        raise ValueError("reported usage unavailable or outside the reviewed bounds")


class SolProvider(OpenAICompatibleProvider):
    def __init__(self, credential: Secret):
        super().__init__(
            "openai",
            "https://api.openai.com/v1",
            credential,
            max_tokens_field="max_completion_tokens",
            supports_structured_output=True,
        )

    def encode(self, request: InferenceRequest) -> WireCall:
        if request != REQUEST:
            raise ValueError("only the fixed one-use request is eligible")
        call = super().encode(request)
        body = json.loads(call.body)
        body.update(reasoning_effort="low", service_tier="default", store=False)
        raw = self.json_body(body)
        if len(raw) > 1024:
            raise ValueError("fixed request exceeded its byte bound")
        return replace(call, body=raw)


def witness(hive: Hive, provider: Provider, client: httpx.Client, out: Path) -> dict[str, Any]:
    """One attempt. Never repairs, retries, falls back or prints model text/credentials."""
    cap = hive.authority().issue(
        "operator:sol",
        "bounded-sol-v1",
        Grant(providers=("openai",), models=(MODEL,), max_calls=1, max_output_tokens=LIMIT),
        120_000,
    )
    report: dict[str, Any] = {"model": MODEL, "requested_limit": LIMIT, "fixture": hive.mode == "test"}
    try:
        result = Inference(hive, client).run(provider, REQUEST, "operator:sol", cap)
        replayed = verify_receipt(hive, result.receipt)
        value = REQUEST.output.validate(replayed.text) if REQUEST.output is not None else {}
        report.update(
            path="VERIFIED",
            schema_valid=True,
            semantic_match=value.get("answer") == EXPECTED,
            receipt_seq=result.receipt.seq,
            input_tokens=replayed.input_tokens,
            output_tokens=replayed.output_tokens,
        )
        try:
            check_usage(replayed.input_tokens, replayed.output_tokens)
        except ValueError:
            report["path"] = "USAGE_UNVERIFIED_OR_OVER_LIMIT"
    except StructuredOutputRejected as exc:
        report.update(path="REJECTED", schema_valid=False, semantic_match=None, receipt_seq=exc.receipt.seq)
    except ProviderError:
        report.update(path="TRANSPORT_OR_PROVIDER_FAILURE", schema_valid=False, semantic_match=None)
    report["events_verified"] = hive.ledger.verify_chain(require_signatures=True)
    # Close before exporting SQLite. No vault, PEM, environment or secret store is exported.
    root = hive.root
    hive.close()
    out.mkdir(parents=True, exist_ok=False)
    shutil.copyfile(root / "hive.json", out / "hive.json")
    (out / "comb").mkdir()
    shutil.copyfile(root / "comb/ledger.sqlite3", out / "comb/ledger.sqlite3")
    if (root / "comb/blobs").exists():
        shutil.copytree(root / "comb/blobs", out / "comb/blobs")
    else:
        (out / "comb/blobs").mkdir()
    (out / "result.json").write_text(json.dumps(report, indent=2) + "\n")
    return report


def replay(root: Path) -> dict[str, Any]:
    manifest = json.loads((root / "hive.json").read_text())
    with Ledger(root / "comb/ledger.sqlite3", HybridLogicalClock("sol_replay")) as ledger:
        hive = Hive(
            root,
            manifest["node_id"],
            manifest["mode"],
            Enclaves(root),
            ledger,
            BlobStore(root / "comb/blobs"),
            Leases(ledger),
        )
        count = ledger.verify_chain(require_signatures=True)
        receipts = list(ledger.events(kind="inference.receipt"))
        spends = list(ledger.events(kind="capability.spent"))
        issues = list(ledger.events(kind="capability.issued"))
        if len(receipts) != 1 or len(spends) != 1 or len(issues) != 1:
            raise ValueError("one issue, receipt and spend required; failure evidence is not a success")
        event = receipts[0]
        cap = Capability.from_json(issues[0].payload)
        grant = cap.grant
        if (
            type(grant.max_calls) is not int
            or grant.max_calls != 1
            or type(grant.max_output_tokens) is not int
            or grant.max_output_tokens != LIMIT
            or grant.providers != ("openai",)
            or grant.models != (MODEL,)
            or grant.tools
            or not issues[0].seq < spends[0].seq < event.seq
            or cap.subject != event.actor
            or spends[0].actor != event.actor
            or cap.issuer != manifest["host_key_id"]
        ):
            raise ValueError("one-call capability scope or ordering mismatch")
        public = public_from_hex(ledger.public_keys()[cap.issuer])
        if not verify(public, canonicalize(cap.body()), cap.signature):
            raise ValueError("capability signature mismatch")
        kind = "fixture" if manifest["mode"] == "test" else "api"
        if (event.payload["provider_kind"], event.payload["provider"], event.payload["codec"]) != (
            kind,
            "openai",
            "openai",
        ):
            raise ValueError("provider classification differs from the declared mode")
        raw = hive.blobs.get(event.payload["request_sha"])
        expected = SolProvider(Secret("offline-verifier-placeholder")).encode(REQUEST).body
        if raw != expected or event.payload["endpoint"] != "https://api.openai.com/v1/chat/completions":
            raise ValueError("request or endpoint differs from the fixed contract")
        result = verify_receipt(hive, event)
        check_usage(result.input_tokens, result.output_tokens)
        return {
            "events_verified": count,
            "path": "VERIFIED",
            "fixture": manifest["mode"] == "test",
            "semantic_match": json.loads(result.text)["answer"] == EXPECTED,
        }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=["live", "replay"])
    parser.add_argument("evidence", type=Path)
    parser.add_argument("--hive", type=Path)
    parser.add_argument("--environment-file", type=Path)
    parser.add_argument("--runs-file", type=Path)
    args = parser.parse_args()
    if args.mode == "replay":
        print(json.dumps(replay(args.evidence), sort_keys=True))
        return
    from bounded_sol_gate import check_files

    if args.hive is None or args.environment_file is None or args.runs_file is None:
        parser.error("live mode requires hive and fresh admission metadata")
    check_files(args.environment_file, args.runs_file)  # before reading the one workflow secret
    key = os.environ.get("OPENAI_API_KEY")
    if not key:
        raise SystemExit("OPENAI_API_KEY missing from the approved environment; no call attempted")
    # No redirects, SDK retries, URL overrides, keyring reads or model tools.
    with httpx.Client(transport=httpx.HTTPTransport(retries=0), follow_redirects=False, timeout=60) as client:
        h = Hive.init(args.hive, "bounded_sol_v1")
        try:
            report = witness(h, SolProvider(Secret(key)), client, args.evidence)
        finally:
            h.close()
    print(json.dumps(report, sort_keys=True))
    if report["path"] != "VERIFIED":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
