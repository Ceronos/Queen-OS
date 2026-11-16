"""One-shot, read-only GitHub issue -> Astra probe -> issue-comment bridge.

NO arbitrary job dispatch, secrets, model calls, background loop or system changes.
Run locally on Astra only after reviewing code; --post is opt-in.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import re
import shutil
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

PROTOCOL = "astra-bridge-v0"
MARKER = "ASTRA-BRIDGE-V0"
RECEIPT_MARKER = "ASTRA-BRIDGE-RECEIPT-V0"
REPO = "Ceronos/Queen-OS"
AUTHOR = "Ceronos"
TITLE = "ASTRA-BRIDGE-REQ: probe"
_MAX_ISSUES = 100
_MAX_BYTES = 250_000


def canonical(value: dict[str, Any]) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=True, separators=(",", ":"))


def validate_request(issue: dict[str, Any], now: datetime, allowed_author: str = AUTHOR) -> dict[str, str] | None:
    """Admit one deliberately harmless, time-limited request; untrusted text is never executed."""
    if issue.get("title") != TITLE or "pull_request" in issue:
        return None
    if issue.get("user", {}).get("login") != allowed_author:
        return None
    body = issue.get("body")
    if not isinstance(body, str) or len(body) > 4096 or not body.startswith(MARKER + "\n"):
        return None
    try:
        request = json.loads(body[len(MARKER) + 1 :])
    except (ValueError, TypeError):
        return None
    if not isinstance(request, dict) or set(request) != {"protocol", "request_id", "kind", "expires_at"}:
        return None
    if request["protocol"] != PROTOCOL or request["kind"] != "probe":
        return None
    request_id = request["request_id"]
    expires_at = request["expires_at"]
    if not isinstance(request_id, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}", request_id):
        return None
    if not isinstance(expires_at, str) or not expires_at.endswith("Z"):
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


def github_issues(repo: str = REPO) -> list[dict[str, Any]]:
    if not re.fullmatch(r"[\w.-]+/[\w.-]+", repo, re.ASCII):
        raise ValueError("invalid repository name")
    url = f"https://api.github.com/repos/{repo}/issues?state=open&sort=created&direction=desc&per_page={_MAX_ISSUES}"
    request = Request(url, headers={"Accept": "application/vnd.github+json", "User-Agent": PROTOCOL})
    with urlopen(request, timeout=12) as response:  # noqa: S310 - fixed HTTPS GitHub API host
        raw = response.read(_MAX_BYTES + 1)
    if len(raw) > _MAX_BYTES:
        raise ValueError("response larger than fixed issue-list limit")
    data = json.loads(raw)
    if not isinstance(data, list):
        raise ValueError("unexpected GitHub response")
    return data


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
        if not separator or len(name) > 120:
            continue
        try:
            memory_mib = int(memory.strip())
        except ValueError:
            continue
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
        "observed_at": at.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
        "kind": "probe_receipt",
        "result": result,
        "result_sha256": hashlib.sha256(canonical(result).encode("utf-8")).hexdigest(),
        "attestation": "none; producer self-report only",
    }
    return RECEIPT_MARKER + "\n" + canonical(payload)


def post_comment(repo: str, issue_number: int, body: str) -> None:
    """Reuse local GitHub CLI authentication; no token extraction or shell execution."""
    if not re.fullmatch(r"[\w.-]+/[\w.-]+", repo, re.ASCII):
        raise ValueError("invalid repository name")
    subprocess.run(  # noqa: S603 - fixed gh executable and API path, no shell
        ["gh", "api", "--method", "POST", f"repos/{repo}/issues/{issue_number}/comments", "-f", f"body={body}"],
        check=True,
        capture_output=True,
        text=True,
        timeout=20,
    )


def load_processed(path: Path) -> set[str]:
    if not path.exists():
        return set()
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list) or not all(isinstance(item, str) for item in data):
        raise ValueError("invalid local processed state; refusing to proceed")
    return set(data)


def save_processed(path: Path, processed: set[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    with tmp.open("w", encoding="utf-8") as handle:
        handle.write(json.dumps(sorted(processed)))
        handle.flush()
    tmp.replace(path)


def run(*, post: bool, state: Path, repo: str = REPO, author: str = AUTHOR) -> int:
    now = datetime.now(timezone.utc)
    processed = load_processed(state)
    admitted = 0
    for issue in github_issues(repo):
        request = validate_request(issue, now, author)
        if request is None:
            continue
        key = f"{request['issue_number']}:{request['request_id']}"
        if key in processed:
            continue
        admitted += 1
        receipt = make_receipt(request, now)
        print(f"Admitted request {key}: {'posting' if post else 'dry-run'}")
        if post:
            post_comment(repo, int(request["issue_number"]), receipt)
            processed.add(key)
            save_processed(state, processed)
            print(f"Posted receipt to issue #{request['issue_number']}; local state updated")
        else:
            print(receipt)
    print(f"Admitted {admitted} pending probe request(s); no additional command types supported")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--post", action="store_true", help="Opt in to authenticated reply via local gh CLI")
    parser.add_argument("--state", type=Path, default=Path.home() / ".local/state/queen-os/astra-bridge-v0.json")
    args = parser.parse_args()
    try:
        return run(post=args.post, state=args.state)
    except (ValueError, OSError, HTTPError, URLError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
        print(f"Bridge refused/failed: {type(e).__name__}: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
