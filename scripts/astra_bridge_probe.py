"""One-shot, read-only GitHub issue -> Astra probe -> issue-comment bridge.

NO arbitrary job dispatch, secrets, model calls, background loop or system changes.
Run locally on Astra only after reviewing code; --post is opt-in.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.request import HTTPRedirectHandler, Request, build_opener

PROTOCOL = "astra-bridge-v0"
MARKER = "ASTRA-BRIDGE-V0"
RECEIPT_MARKER = "ASTRA-BRIDGE-RECEIPT-V0"
REPO = "Ceronos/Queen-OS"
AUTHOR = "Ceronos"
TITLE = "ASTRA-BRIDGE-REQ: probe"
_MAX_BYTES = 250_000
_ID_PATTERN = r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}"


def canonical(value: dict[str, Any]) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=True, separators=(",", ":"))


def unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    data = dict(pairs)
    if len(data) != len(pairs):
        raise ValueError("duplicate JSON field")
    return data


def validate_request(issue: dict[str, Any], now: datetime, allowed_author: str = AUTHOR) -> dict[str, str] | None:
    """Admit one deliberately harmless, time-limited request; untrusted text is never executed."""
    if issue.get("state") != "open" or issue.get("title") != TITLE or "pull_request" in issue:
        return None
    user = issue.get("user")
    if not isinstance(user, dict) or user.get("login") != allowed_author:
        return None
    body = issue.get("body")
    if not isinstance(body, str) or len(body) > 4096 or not body.startswith(MARKER + "\n"):
        return None
    try:
        request = json.loads(body[len(MARKER) + 1 :], object_pairs_hook=unique_object)
    except (ValueError, RecursionError):
        return None
    if not isinstance(request, dict) or set(request) != {"protocol", "request_id", "kind", "expires_at"}:
        return None
    if request["protocol"] != PROTOCOL or request["kind"] != "probe":
        return None
    request_id = request["request_id"]
    expires_at = request["expires_at"]
    if not isinstance(request_id, str) or not re.fullmatch(_ID_PATTERN, request_id):
        return None
    if not isinstance(expires_at, str) or not re.fullmatch(
        r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z", expires_at
    ):
        return None
    try:
        expiration = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
    except ValueError:
        return None
    if not timedelta(0) < expiration - now <= timedelta(days=7):
        return None
    number = issue.get("number")
    if type(number) is not int or not 1 <= number <= 2**31 - 1:
        return None
    return {"request_id": request_id, "issue_number": str(number)}


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def github_read(issue_number: int, *, comments: bool = False) -> Any:
    if type(issue_number) is not int or not 1 <= issue_number <= 2**31 - 1:
        raise ValueError("invalid issue number")
    url = f"https://api.github.com/repos/{REPO}/issues/{issue_number}"
    if comments:
        url += "/comments?per_page=100"
    request = Request(  # noqa: S310 - fixed HTTPS GitHub API host and numeric issue path
        url, headers={"Accept": "application/vnd.github+json", "User-Agent": PROTOCOL}
    )
    with build_opener(NoRedirect()).open(request, timeout=12) as response:
        if comments and 'rel="next"' in response.headers.get("Link", ""):
            raise ValueError("comment lookup exceeds one page")
        raw = response.read(_MAX_BYTES + 1)
    if len(raw) > _MAX_BYTES:
        raise ValueError("GitHub response exceeds fixed limit")
    return json.loads(raw)


def gpu_summary() -> dict[str, Any]:
    binary = shutil.which("nvidia-smi")
    if binary is None:
        return {"status": "unavailable"}
    try:
        result = subprocess.run(  # noqa: S603 - fixed, read-only hardware inventory command
            [binary, "--query-gpu=name,memory.total", "--format=csv,noheader,nounits"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return {"status": "unavailable"}
    if result.returncode != 0:
        return {"status": "unavailable"}
    devices = []
    for line in result.stdout.splitlines()[:4]:
        name, separator, memory = line.rpartition(",")
        if not separator or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9 .()+/_-]{0,119}", name.strip()):
            continue
        try:
            memory_mib = int(memory.strip())
        except ValueError:
            continue
        if 0 < memory_mib <= 2**24:
            devices.append({"name": name.strip(), "memory_mib": memory_mib})
    return {"status": "detected", "devices": devices} if devices else {"status": "unavailable"}


def make_receipt(request: dict[str, str], at: datetime, gpu: dict[str, Any] | None = None) -> str:
    """No hostname, IP, serial numbers, environment, paths or credentials are collected."""
    result = {
        "os": platform.system(),
        "architecture": platform.machine(),
        "python": f"{sys.version_info.major}.{sys.version_info.minor}",
        "gpu": gpu if gpu is not None else gpu_summary(),
    }
    payload = {
        "protocol": PROTOCOL,
        "request_id": request["request_id"],
        "issue_number": int(request["issue_number"]),
        "observed_at": at.astimezone(UTC).isoformat().replace("+00:00", "Z"),
        "kind": "probe_receipt",
        "result": result,
        "result_sha256": hashlib.sha256(canonical(result).encode("utf-8")).hexdigest(),
        "attestation": "none; producer self-report only",
    }
    return RECEIPT_MARKER + "\n" + canonical(payload)


def github_cli(*args: str) -> str:
    binary = shutil.which("gh")
    if binary is None:
        raise OSError("GitHub CLI is unavailable")
    result = subprocess.run(  # noqa: S603 - fixed executable and API arguments, no shell
        [binary, "api", "--hostname", "github.com", *args],
        check=True,
        capture_output=True,
        text=True,
        timeout=20,
        env={**os.environ, "GH_PROMPT_DISABLED": "1"},
    )
    return result.stdout


def receipt_exists(issue_number: int, request_id: str, login: str) -> bool:
    comments = github_read(issue_number, comments=True)
    if not isinstance(comments, list):
        raise ValueError("unexpected GitHub comment response")
    for comment in comments:
        if not isinstance(comment, dict):
            raise ValueError("unexpected GitHub comment")
        user = comment.get("user")
        body = comment.get("body")
        if not isinstance(user, dict) or user.get("login") != login or not isinstance(body, str):
            continue
        if not body.startswith(RECEIPT_MARKER + "\n"):
            continue
        receipt = json.loads(body.split("\n", 1)[1], object_pairs_hook=unique_object)
        if not isinstance(receipt, dict):
            raise ValueError("unexpected receipt format")
        if receipt.get("issue_number") == issue_number and receipt.get("request_id") == request_id:
            return True
    return False


def load_processed(path: Path) -> set[str]:
    if not path.exists():
        return set()
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list) or not all(isinstance(item, str) for item in data):
        raise ValueError("invalid local processed state; refusing to proceed")
    return set(data)


def save_processed(path: Path, processed: set[str]) -> None:
    with tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8", dir=path.parent, prefix=path.name + ".", delete=False
    ) as handle:
        tmp = Path(handle.name)
        try:
            handle.write(json.dumps(sorted(processed)))
            handle.close()
            tmp.replace(path)
        finally:
            tmp.unlink(missing_ok=True)


def run(*, issue_number: int, request_id: str, post: bool, state: Path) -> int:
    issue = github_read(issue_number)
    now = datetime.now(UTC)
    expected = {"issue_number": str(issue_number), "request_id": request_id}
    if not isinstance(issue, dict) or validate_request(issue, now) != expected:
        print("Bridge refused: issue does not match the requested open, unexpired probe", file=sys.stderr)
        return 2

    key = f"{issue_number}:{request_id}"
    if not post:
        print(f"Admitted request {key}: dry-run")
        print(make_receipt(expected, now))
        return 0

    state.parent.mkdir(parents=True, exist_ok=True)
    lock = state.with_name(state.name + ".lock")
    lock.mkdir(mode=0o700)
    try:
        processed = load_processed(state)
        if key in processed:
            print(f"Receipt already recorded locally for {key}")
            return 0
        login = github_cli("user", "--jq", ".login").strip()
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9-]{0,38}", login):
            raise ValueError("could not identify the GitHub CLI account")
        if receipt_exists(issue_number, request_id, login):
            print(f"Receipt already exists on GitHub for {key}")
        else:
            fresh_issue = github_read(issue_number)
            now = datetime.now(UTC)
            if not isinstance(fresh_issue, dict) or validate_request(fresh_issue, now) != expected:
                raise ValueError("request changed or expired before posting")
            receipt = make_receipt(expected, now)
            github_cli("--method", "POST", f"repos/{REPO}/issues/{issue_number}/comments", "-f", f"body={receipt}")
            print(f"Posted receipt to issue #{issue_number}")
        save_processed(state, processed | {key})
    finally:
        lock.rmdir()
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--issue", type=int, required=True, help="Exact Queen-OS issue number")
    parser.add_argument("--request-id", required=True, help="Exact request ID from the authorized issue")
    parser.add_argument("--post", action="store_true", help="Opt in to authenticated reply via local gh CLI")
    parser.add_argument("--state", type=Path, default=Path.home() / ".local/state/queen-os/astra-bridge-v0.json")
    args = parser.parse_args()
    try:
        return run(issue_number=args.issue, request_id=args.request_id, post=args.post, state=args.state)
    except (ValueError, OSError, RecursionError, subprocess.SubprocessError) as e:
        print(f"Bridge refused/failed ({type(e).__name__}). Check the issue before retrying a post.", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
