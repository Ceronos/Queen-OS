"""One-use Sol dispatch admission. No model, credential or keyring access."""

from __future__ import annotations

import json
import os
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def authorize(
    context: dict[str, str], event: dict[str, Any], environment: dict[str, Any], listing: dict[str, Any], now: datetime
) -> None:
    if (context.get("GITHUB_EVENT_NAME"), context.get("GITHUB_REF"), context.get("GITHUB_ACTOR")) != (
        "workflow_dispatch",
        "refs/heads/main",
        "Ceronos",
    ):
        raise ValueError("explicit owner dispatch on main required")
    sha = context.get("GITHUB_SHA", "")
    inputs = event.get("inputs", {})
    if not re.fullmatch("[0-9a-f]{40}", sha) or inputs.get("approved_commit_sha") != sha:
        raise ValueError("exact approved revision required")
    if inputs.get("confirm_billable_sol") != "true" or inputs.get("confirm_usd_005") != "true":
        raise ValueError("explicit one-call and USD 0.05 allowance confirmations required")
    if context.get("GITHUB_RUN_ATTEMPT") != "1":
        raise ValueError("reruns are forbidden, including after cancellation or failure")
    if now.tzinfo is None or now >= datetime(2026, 11, 10, tzinfo=UTC):
        raise ValueError("one-use proposal expired or clock unavailable")
    if environment.get("name") != "live-inference" or not isinstance(environment.get("protection_rules"), list):
        raise ValueError("existing live-inference environment metadata required; do not create or weaken it")
    runs = listing.get("workflow_runs")
    if not isinstance(runs, list) or type(listing.get("total_count")) is not int or listing["total_count"] != len(runs):
        raise ValueError("complete lifetime workflow history required")
    ids: list[int] = []
    for run in runs:
        if not isinstance(run, dict) or type(run.get("id")) is not int or run["id"] <= 0:
            raise ValueError("invalid workflow history")
        ids.append(run["id"])
    if not ids or len(set(ids)) != len(ids):
        raise ValueError("invalid workflow history")
    run_id = context.get("GITHUB_RUN_ID", "")
    if not run_id.isdecimal() or int(run_id) not in ids or int(run_id) != min(ids):
        raise ValueError("first workflow run only; every earlier run consumes this one-use slot")


def check_files(environment_file: Path, runs_file: Path) -> None:
    authorize(
        dict(os.environ),
        json.loads(Path(os.environ["GITHUB_EVENT_PATH"]).read_text()),
        json.loads(environment_file.read_text()),
        json.loads(runs_file.read_text()),
        datetime.now(UTC),
    )


if __name__ == "__main__":
    import sys

    check_files(Path(sys.argv[1]), Path(sys.argv[2]))
    print("One-use Sol admission passed; no inference performed by admission.")
