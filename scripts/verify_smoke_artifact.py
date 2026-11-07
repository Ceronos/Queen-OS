"""Verify an archived, keyless Ollama smoke bundle without contacting any model.

The caller must obtain the expected ZIP digest from a separate trusted receipt
(for example the GitHub artifact API). Embedded keys prove attribution only; this
tool neither authenticates a model server nor accepts an isolation boundary.
"""

from __future__ import annotations

import argparse
import io
import json
import re
import stat
import tempfile
import zipfile
from pathlib import Path, PurePosixPath
from typing import Any

from queen_os.authority.tokens import ISSUED, SPENT, Capability
from queen_os.comb.blobs import BlobStore
from queen_os.comb.enclaves import Enclaves
from queen_os.comb.hlc import HLCStamp, HybridLogicalClock
from queen_os.comb.leases import Leases
from queen_os.comb.ledger import Ledger
from queen_os.crypto.keys import public_from_hex, verify
from queen_os.hive import Hive
from queen_os.providers.receipt import RECEIPT_KIND, verify_receipt
from queen_os.serial.afser import sha256_hex
from queen_os.serial.jcs import canonicalize

MAX_ZIP_BYTES = 1024 * 1024
MAX_MEMBER_BYTES = 2 * 1024 * 1024
MAX_TOTAL_BYTES = 4 * 1024 * 1024
_SHA = re.compile(r"[0-9a-f]{64}")


def _extract(raw: bytes, root: Path) -> None:
    """Only the public canary evidence layout is admitted, into a new temp root."""
    with zipfile.ZipFile(io.BytesIO(raw)) as bundle:
        seen: set[str] = set()
        total = 0
        for member in bundle.infolist():
            name = member.filename
            path = PurePosixPath(name)
            if name in seen or "\\" in name or path.is_absolute() or ".." in path.parts:
                raise ValueError("duplicate or unsafe archive member")
            if str(path) != name or member.is_dir() or stat.S_IFMT(member.external_attr >> 16) not in (0, stat.S_IFREG):
                raise ValueError("archive must contain ordinary flat evidence files")
            blob = re.fullmatch(r"comb/blobs/([0-9a-f]{2})/([0-9a-f]{64})", name)
            if name not in {"comb/ledger.sqlite3", "hive.json", "ollama-version.txt"} and not blob:
                raise ValueError("unexpected evidence member (vault/private keys are never allowed)")
            if blob and blob[1] != blob[2][:2]:
                raise ValueError("blob directory does not match its address")
            total += member.file_size
            if member.file_size > MAX_MEMBER_BYTES or total > MAX_TOTAL_BYTES:
                raise ValueError("expanded evidence exceeds review limits")
            data = bundle.read(member)
            if len(data) != member.file_size:
                raise ValueError("archive member size mismatch")
            target = root.joinpath(*path.parts)
            target.parent.mkdir(parents=True, exist_ok=True)
            with target.open("xb") as output:
                output.write(data)
            seen.add(name)
        if not {"hive.json", "comb/ledger.sqlite3"} <= seen:
            raise ValueError("missing hive or ledger")


def _verify_hive(root: Path, expected_word: str | None) -> dict[str, Any]:
    manifest = json.loads((root / "hive.json").read_bytes())
    if manifest.get("format") != 1 or manifest.get("mode") != "production":
        raise ValueError("only a production-mode canary bundle is eligible")
    # Existing Ledger may initialize/migrate SQLite housekeeping. It operates on
    # this disposable extraction only; the externally pinned ZIP is never edited.
    with Ledger(root / "comb/ledger.sqlite3", HybridLogicalClock("smoke_review")) as ledger:
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
        genesis = ledger.get(1)
        if genesis is None or genesis.kind != "hive.genesis" or genesis.payload.get("mode") != "production":
            raise ValueError("missing signed production genesis")
        host = manifest["host_key_id"]
        if genesis.signer != host or genesis.payload.get("host_key_id") != host:
            raise ValueError("hive manifest and signed genesis disagree")
        if any(event.signer != host for event in ledger.events()):
            raise ValueError("the smoke bundle contains a foreign event signer")
        receipts = list(ledger.events(kind=RECEIPT_KIND))
        spends = list(ledger.events(kind=SPENT))
        issued = list(ledger.events(kind=ISSUED))
        if len(receipts) != 1 or len(spends) != 1 or len(issued) != 1:
            raise ValueError("exactly one issued capability, spend and inference receipt are required")
        receipt, spend, issue = receipts[0], spends[0], issued[0]
        p = receipt.payload
        if (p.get("provider_kind"), p.get("provider"), p.get("codec")) != ("local", "ollama", "ollama"):
            raise ValueError("fixture, hosted or unknown provider is not a keyless local smoke")
        if p.get("credential_fp") is not None or p.get("http_status") != 200:
            raise ValueError("credential-bearing or unsuccessful inference")
        if p.get("endpoint") not in {"http://localhost:11434/api/chat", "http://127.0.0.1:11434/api/chat"}:
            raise ValueError("unexpected inference endpoint")
        cap = Capability.from_json(issue.payload)
        if cap.to_json() != issue.payload or cap.issuer != host:
            raise ValueError("capability encoding/issuer mismatch")
        public = public_from_hex(ledger.public_keys()[cap.issuer])
        if not verify(public, canonicalize(cap.body()), cap.signature):
            raise ValueError("capability signature does not verify")
        grant = cap.grant
        model = p["model_requested"]
        if grant.max_calls != 1 or grant.providers != ("ollama",) or grant.models != (model,) or grant.tools:
            raise ValueError("capability is not scoped to exactly one tool-free model call")
        if not 1 <= grant.max_output_tokens <= 32 or cap.subject != receipt.actor or spend.actor != receipt.actor:
            raise ValueError("smoke token/subject scope mismatch")
        if not issue.seq < spend.seq < receipt.seq or spend.payload.get("n") != 1:
            raise ValueError("capability reservation ordering/count mismatch")
        used_ms = HLCStamp.decode(spend.hlc).wall_ms
        if not cap.not_before_ms <= used_ms < cap.expires_ms:
            raise ValueError("capability spend was outside its validity window")
        result = verify_receipt(hive, receipt)
        request = json.loads(hive.blobs.get(p["request_sha"]))
        response = json.loads(hive.blobs.get(p["response_sha"]))
        if set(request) - {"model", "messages", "stream", "options", "keep_alive"}:
            raise ValueError("unexpected request fields, tools or session state")
        messages = request.get("messages")
        if not isinstance(messages, list) or len(messages) not in (1, 2):
            raise ValueError("smoke request must contain only its declared prompt")
        roles = [m.get("role") for m in messages]
        if roles not in (["user"], ["system", "user"]):
            raise ValueError("history or undeclared message role in smoke request")
        if any(set(m) != {"role", "content"} or not isinstance(m["content"], str) for m in messages):
            raise ValueError("unexpected message fields")
        if len(canonicalize(messages)) > 4096:
            raise ValueError("smoke prompt exceeds the review size bound")
        limit = request.get("options", {}).get("num_predict")
        if type(limit) is not int or not 1 <= limit <= grant.max_output_tokens:
            raise ValueError("wire output limit is not covered by the capability")
        if request.get("model") != model or request.get("stream") is not False:
            raise ValueError("wire model or streaming mode mismatch")
        if response.get("done") is not True or not result.text.strip():
            raise ValueError("model response was incomplete or empty")
        if type(result.output_tokens) is not int or not 1 <= result.output_tokens <= limit:
            raise ValueError("observed output count is unknown or exceeds the request bound")
        answer_ok = None if expected_word is None else result.text.strip().casefold().rstrip(".!?") == expected_word
        status = "ARCHIVED_INFERENCE_PATH_VERIFIED"
        if answer_ok is not None:
            status = "ARCHIVED_SMOKE_PASS" if answer_ok else "ARCHIVED_SMOKE_ANSWER_MISMATCH"
        return {
            "status": status,
            "scope": "One exported keyless local inference; no new inference was performed by this verifier.",
            "events_verified": count,
            "host_key_id": host,
            "receipt_seq": receipt.seq,
            "receipt_hash": receipt.hash,
            "provider": p["provider"],
            "model": model,
            "reply": result.text,
            "answer_check": {"expected_word": expected_word, "passed": answer_ok},
            "input_tokens": result.input_tokens,
            "output_tokens": result.output_tokens,
            "requested_output_limit": limit,
            "capability_max_calls": grant.max_calls,
            "request_sha256": p["request_sha"],
            "response_sha256": p["response_sha"],
            "limitations": [
                "Archive/run provenance depends on the separately trusted expected digest.",
                "Embedded signatures prove attribution, not model-server authenticity or truth.",
                "This verifier does not validate host.probe hardware/clock claims.",
                "No containment, provider freshness, A/B/C fairness or independent security acceptance is established.",
                "The exported hive accounts for one call; it does not count calls in other hives/jobs.",
            ],
        }


def verify_archive(archive: Path, expected_sha256: str, expected_word: str | None = None) -> dict[str, Any]:
    if _SHA.fullmatch(expected_sha256) is None:
        raise ValueError("an external 64-character lowercase SHA-256 is required")
    if expected_word is not None and re.fullmatch(r"[a-z]{1,32}", expected_word) is None:
        raise ValueError("expected_word must be an explicit lowercase ASCII word")
    if archive.stat().st_size > MAX_ZIP_BYTES:
        raise ValueError("compressed evidence exceeds review limit")
    raw = archive.read_bytes()
    if sha256_hex(raw) != expected_sha256:
        raise ValueError("archive digest does not match the external receipt")
    with tempfile.TemporaryDirectory(prefix="queen-smoke-review-") as directory:
        root = Path(directory)
        _extract(raw, root)
        result = _verify_hive(root, expected_word)
    if sha256_hex(archive.read_bytes()) != expected_sha256:
        raise ValueError("archive changed during verification")
    return {**result, "archive_sha256": expected_sha256}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path)
    parser.add_argument("--expected-sha256", required=True)
    parser.add_argument("--expect-word", help="add an explicit answer oracle; mismatches exit with status 2")
    args = parser.parse_args()
    result = verify_archive(args.archive, args.expected_sha256, args.expect_word)
    print(json.dumps(result, indent=2))
    if result["status"] == "ARCHIVED_SMOKE_ANSWER_MISMATCH":
        raise SystemExit(2)


if __name__ == "__main__":
    main()
