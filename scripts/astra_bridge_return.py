"""Explicit one-shot connector relay and independent readback; never posts or dispatches work."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import astra_bridge_probe as probe

MARKER = "ASTRA-BRIDGE-RETURN-V1"
ACK_MARKER = "ASTRA-BRIDGE-ACK-V1"
ACCOUNT = {"login": "Ceronos", "id": 202629591}
SCOPE = "probe-receipt-only; real-agent NO-GO"
PROVENANCE = "operator-mediated connector relay; GitHub authenticates poster, not host or Sage identity"
LIMIT = 16_384


def digest(value: Any) -> str:
    return hashlib.sha256(probe.canonical(value).encode()).hexdigest()


def decode(body: str, marker: str) -> dict[str, Any]:
    if not isinstance(body, str) or len(body.encode()) > LIMIT or not body.startswith(marker + "\n"):
        raise ValueError("invalid bounded envelope")
    value = json.loads(body.split("\n", 1)[1], object_pairs_hook=probe.unique_object)
    if not isinstance(value, dict):
        raise ValueError("envelope must be an object")
    return value


def stamp(value: Any) -> datetime:
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(?:\.\d{1,6})?Z", value):
        raise ValueError("invalid UTC timestamp")
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def validate_probe(receipt: dict[str, Any], issue: dict[str, Any], now: datetime) -> None:
    fields = {"protocol", "request_id", "issue_number", "observed_at", "kind", "result", "result_sha256", "attestation"}
    request = probe.validate_request(issue, now)
    if not request or set(receipt) != fields or any(issue.get("user", {}).get(k) != v for k, v in ACCOUNT.items()):
        raise ValueError("invalid probe receipt or expired request")
    if (
        receipt["protocol"] != probe.PROTOCOL
        or receipt["kind"] != "probe_receipt"
        or receipt["request_id"] != request["request_id"]
        or type(receipt["issue_number"]) is not int
        or receipt["issue_number"] != issue["number"]
        or receipt["attestation"] != "none; producer self-report only"
    ):
        raise ValueError("probe receipt does not match request")
    if not stamp(issue["created_at"]) <= stamp(receipt["observed_at"]) <= now:
        raise ValueError("observation outside request window")
    result = receipt["result"]
    if not isinstance(result, dict) or set(result) != {"os", "architecture", "python", "gpu"}:
        raise ValueError("unexpected probe fields")
    if result["os"] not in ("Linux", "Darwin", "Windows"):
        raise ValueError("unsupported OS family")
    for key, pattern in (("architecture", r"[A-Za-z0-9_-]{1,32}"), ("python", r"3\.\d{1,2}")):
        if not isinstance(result[key], str) or not re.fullmatch(pattern, result[key]):
            raise ValueError("invalid bounded platform value")
    gpu = result["gpu"]
    if gpu != {"status": "unavailable"}:
        if not isinstance(gpu, dict) or set(gpu) != {"status", "devices"} or gpu["status"] != "detected":
            raise ValueError("unexpected GPU fields")
        devices = gpu["devices"]
        if not isinstance(devices, list) or not 1 <= len(devices) <= 4:
            raise ValueError("invalid GPU count")
        for device in devices:
            if not isinstance(device, dict) or set(device) != {"name", "memory_mib"}:
                raise ValueError("unexpected device fields")
            if not isinstance(device["name"], str) or not re.fullmatch(
                r"[A-Za-z0-9][A-Za-z0-9 .()+/_-]{0,119}", device["name"]
            ):
                raise ValueError("invalid GPU name")
            if type(device["memory_mib"]) is not int or not 0 < device["memory_mib"] <= 2**24:
                raise ValueError("invalid GPU memory")
    if receipt["result_sha256"] != digest(result):
        raise ValueError("probe digest mismatch")


def validate_return(body: str, issue: dict[str, Any], now: datetime) -> dict[str, Any]:
    value = decode(body, MARKER)
    if set(value) != {
        "protocol",
        "repository",
        "issue_number",
        "request_id",
        "request_body_sha256",
        "handoff_marker",
        "source_sha256",
        "posting_account",
        "provenance",
        "scope",
        "probe_receipt",
    }:
        raise ValueError("unexpected relay fields")
    if (
        value["protocol"] != "astra-bridge-return-v1"
        or value["repository"] != probe.REPO
        or value["posting_account"] != ACCOUNT
        or value["scope"] != SCOPE
        or value["provenance"] != PROVENANCE
        or type(value["issue_number"]) is not int
        or value["issue_number"] != issue["number"]
        or value["request_body_sha256"] != hashlib.sha256(issue["body"].encode()).hexdigest()
    ):
        raise ValueError("relay scope or request mismatch")
    if not isinstance(value["handoff_marker"], str) or not re.fullmatch(
        r"SAGE-BRIDGE-\d{8}-\d{6}Z", value["handoff_marker"]
    ):
        raise ValueError("invalid handoff marker")
    sources = value["source_sha256"]
    if not isinstance(sources, dict) or set(sources) != {"astra_bridge_probe.py", "astra_bridge_return.py"}:
        raise ValueError("invalid source references")
    if any(not isinstance(h, str) or not re.fullmatch(r"[a-f0-9]{64}", h) for h in sources.values()):
        raise ValueError("invalid source digest")
    receipt = value["probe_receipt"]
    if not isinstance(receipt, dict) or value["request_id"] != receipt.get("request_id"):
        raise ValueError("relay request ID mismatch")
    validate_probe(receipt, issue, now)
    return value


def prepare(issue: dict[str, Any], request_id: str, marker: str, now: datetime) -> str:
    request = probe.validate_request(issue, now)
    if not request or request["request_id"] != request_id:
        raise ValueError("request does not match operator selection")
    receipt = decode(probe.make_receipt(request, now), probe.RECEIPT_MARKER)
    sources = {
        name: hashlib.sha256(Path(__file__).with_name(name).read_bytes()).hexdigest()
        for name in ("astra_bridge_probe.py", "astra_bridge_return.py")
    }
    value = {
        "protocol": "astra-bridge-return-v1",
        "repository": probe.REPO,
        "issue_number": issue["number"],
        "request_id": request_id,
        "request_body_sha256": hashlib.sha256(issue["body"].encode()).hexdigest(),
        "handoff_marker": marker,
        "source_sha256": sources,
        "posting_account": ACCOUNT,
        "provenance": PROVENANCE,
        "scope": SCOPE,
        "probe_receipt": receipt,
    }
    body = MARKER + "\n" + probe.canonical(value)
    validate_return(body, issue, now)
    return body


def find_exact(body: str, comments: Any, *, marker: str, issue_number: int, request_id: str) -> dict[str, Any]:
    """One exact unedited comment by the pinned account; conflicting duplicates fail closed."""
    if not isinstance(comments, list) or len(comments) > 100:
        raise ValueError("unbounded comment response")
    matches = []
    for comment in comments:
        if not isinstance(comment, dict):
            raise ValueError("unexpected comment response")
        user = comment.get("user")
        if not isinstance(user, dict) or any(user.get(k) != v for k, v in ACCOUNT.items()):
            continue
        candidate = comment.get("body")
        if not isinstance(candidate, str) or not candidate.startswith(marker + "\n"):
            continue
        value = decode(candidate, marker)
        if value.get("issue_number") != issue_number or value.get("request_id") != request_id:
            continue
        comment_id = comment.get("id")
        if type(comment_id) is not int or comment_id <= 0:
            raise ValueError("invalid comment ID")
        url = f"https://github.com/{probe.REPO}/issues/{issue_number}#issuecomment-{comment_id}"
        if candidate != body or comment.get("html_url") != url:
            raise ValueError("conflicting receipt or repository URL")
        if not comment.get("created_at") or comment.get("updated_at") != comment["created_at"]:
            raise ValueError("edited receipt requires manual reconciliation")
        stamp(comment["created_at"])
        matches.append(comment)
    if len(matches) != 1:
        raise ValueError("expected exactly one matching receipt")
    return matches[0]


def acknowledgment(value: dict[str, Any], body: str, comment: dict[str, Any]) -> str:
    return (
        ACK_MARKER
        + "\n"
        + probe.canonical(
            {
                "protocol": "astra-bridge-ack-v1",
                "repository": probe.REPO,
                "issue_number": value["issue_number"],
                "request_id": value["request_id"],
                "handoff_marker": value["handoff_marker"],
                "receipt_comment_id": comment["id"],
                "receipt_body_sha256": hashlib.sha256(body.encode()).hexdigest(),
                "scope": SCOPE,
                "provenance": "connector account acknowledgment; Sage session identity not attested",
            }
        )
    )


def run(args: argparse.Namespace) -> int:
    issue = probe.github_read(args.issue)
    if not isinstance(issue, dict) or issue.get("number") != args.issue:
        raise ValueError("unexpected issue response")
    now = datetime.now(UTC)
    if args.command == "prepare":
        body = prepare(issue, args.request_id, args.handoff_marker, now)
        # Exclusive creation prevents silent replacement of an operator's expected receipt.
        with args.output.open("x", encoding="utf-8", newline="") as handle:
            handle.write(body)
        print(f"Prepared relay only; SHA-256 {hashlib.sha256(body.encode()).hexdigest()}")
        return 0
    if args.receipt.stat().st_size > LIMIT:
        raise ValueError("receipt file exceeds limit")
    body = args.receipt.read_text(encoding="utf-8")
    value = validate_return(body, issue, now)
    if value["request_id"] != args.request_id:
        raise ValueError("request ID does not match operator selection")
    comments = probe.github_read(args.issue, comments=True)
    comment = find_exact(body, comments, marker=MARKER, issue_number=args.issue, request_id=args.request_id)
    if stamp(comment["created_at"]) < stamp(value["probe_receipt"]["observed_at"]):
        raise ValueError("comment predates observation")
    ack = acknowledgment(value, body, comment)
    if args.command == "verify-ack":
        found = find_exact(ack, comments, marker=ACK_MARKER, issue_number=args.issue, request_id=args.request_id)
        if stamp(found["created_at"]) < stamp(comment["created_at"]):
            raise ValueError("acknowledgment predates receipt")
        print(f"Verified account acknowledgment: {found['html_url']}; host/Sage identity not attested")
    else:
        print(f"Verified exact connector relay: {comment['html_url']}; host identity not attested")
        print(ack)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("prepare", "verify", "verify-ack"):
        command = commands.add_parser(name)
        command.add_argument("--issue", required=True, type=int)
        command.add_argument("--request-id", required=True)
        if name == "prepare":
            command.add_argument("--handoff-marker", required=True)
            command.add_argument("--output", required=True, type=Path)
        else:
            command.add_argument("--receipt", required=True, type=Path)
    try:
        return run(parser.parse_args())
    except (ValueError, OSError, KeyError, TypeError, RecursionError) as error:
        print(f"Return bridge refused/failed ({type(error).__name__}); reconcile before retrying", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
