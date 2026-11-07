"""Fail-closed admission for the separate, manually dispatched live CI workflow.

This verifies workflow intent and environment configuration, not containment or
the truth of the human authorization record. It never contacts a model or keyring.

Two admission modes:

* **Reviewer mode** (Sage, PR #3): ``authorization_ref`` is an HTTPS record, and the
  ``live-inference`` environment requires reviewers with self-review prevention.
* **Standing-order mode** (owner order SO-0001, QOS-0003): ``authorization_ref`` is
  ``standing-order:<id>``. The order is read from ``governance/`` **at the approved main
  commit**, so changing scope requires a merge to main. The request must fall inside the
  order's provider/model/token scope and its daily run budget, and the dispatching
  engineer must be named in the order.
"""

from __future__ import annotations

import argparse
import fnmatch
import json
import os
import re
from pathlib import Path
from typing import Any

STANDING_PREFIX = "standing-order:"


def _standing_order(
    inputs: dict[str, Any],
    authorization: str,
    provider: str,
    model: str,
    tokens: str,
    environment: dict[str, Any],
    order: dict[str, Any] | None,
    runs_today: int | None,
) -> dict[str, str]:
    order_id = authorization[len(STANDING_PREFIX) :]
    if not isinstance(order, dict) or order.get("order_id") != order_id:
        raise ValueError(f"standing order {order_id!r} not found in governance/ at the approved commit")
    if order.get("status") != "active":
        raise ValueError(f"standing order {order_id} is not active")
    engineer = inputs.get("engineer")
    if engineer not in order.get("engineers", []):
        raise ValueError(f"engineer {engineer!r} is not named in standing order {order_id}")
    patterns = order.get("scope", {}).get(provider)
    if not isinstance(patterns, list) or not any(fnmatch.fnmatchcase(model, p) for p in patterns):
        raise ValueError(f"{provider}/{model} is outside standing order {order_id}")
    if int(tokens) > int(order.get("max_output_tokens", 0)):
        raise ValueError(f"max_tokens {tokens} exceeds standing order {order_id}")
    if runs_today is None or runs_today < 0:
        raise ValueError("today's run count could not be established; refusing (fail closed)")
    if runs_today >= int(order.get("max_runs_per_utc_day", 0)):
        raise ValueError(f"daily run budget of standing order {order_id} is exhausted")
    if environment.get("name") != "live-inference":
        raise ValueError("the existing live-inference environment must be verified")
    for rule in environment.get("protection_rules") or []:
        if isinstance(rule, dict) and rule.get("type") == "required_reviewers" and rule.get("prevent_self_review"):
            raise ValueError(
                "environment requires self-review prevention, which deadlocks standing-order dispatches "
                "made through the owner's account; remove that rule or use reviewer mode"
            )
    return {
        "provider": provider,
        "model": model,
        "max_tokens": tokens,
        "authorization_ref": authorization,
        "engineer": str(engineer),
        "mode": "standing-order",
    }


def authorize_dispatch(
    event: dict[str, Any],
    event_name: str,
    ref: str,
    sha: str,
    environment: dict[str, Any],
    standing_order: dict[str, Any] | None = None,
    runs_today: int | None = None,
) -> dict[str, str]:
    """Validate actual GitHub metadata before any live installation or inference."""
    if event_name != "workflow_dispatch" or ref != "refs/heads/main":
        raise ValueError("only an explicit dispatch on main is eligible")
    inputs = event.get("inputs")
    if not isinstance(inputs, dict) or inputs.get("confirm_live_inference") != "true":
        raise ValueError("explicit live-inference confirmation is required")
    if re.fullmatch(r"[0-9a-f]{40}", sha) is None or inputs.get("approved_commit_sha") != sha:
        raise ValueError("the dispatched commit must exactly match the approved commit")
    authorization = inputs.get("authorization_ref", "")
    standing = isinstance(authorization, str) and re.fullmatch(r"standing-order:SO-\d{4}", authorization) is not None
    if not standing and (
        not isinstance(authorization, str) or re.fullmatch(r"https://[^\s]{1,2000}", authorization) is None
    ):
        raise ValueError("an HTTPS authorization record is required; its content must be reviewed by a maintainer")
    provider = inputs.get("provider")
    if provider not in {"ollama", "anthropic", "openai", "gemini"}:
        raise ValueError("unsupported provider")
    model = inputs.get("model", "")
    if not isinstance(model, str) or re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:/@-]{0,127}", model) is None:
        raise ValueError("an explicit bounded model identifier is required")
    tokens = inputs.get("max_tokens", "")
    if not isinstance(tokens, str) or re.fullmatch(r"[1-9][0-9]{0,2}", tokens) is None or int(tokens) > 128:
        raise ValueError("max_tokens must be a canonical integer from 1 through 128")
    if standing:
        return _standing_order(inputs, authorization, provider, model, tokens, environment, standing_order, runs_today)
    if environment.get("name") != "live-inference":
        raise ValueError("the existing live-inference environment must be verified")
    rules = environment.get("protection_rules")
    if not isinstance(rules, list):
        raise ValueError("environment protection metadata is missing")
    for rule in rules:
        if not isinstance(rule, dict) or rule.get("type") != "required_reviewers":
            continue
        reviewers = rule.get("reviewers")
        if rule.get("prevent_self_review") is True and isinstance(reviewers, list):
            valid = [
                reviewer
                for reviewer in reviewers
                if isinstance(reviewer, dict)
                and reviewer.get("type") in {"User", "Team"}
                and isinstance(reviewer.get("reviewer"), dict)
                and type(reviewer["reviewer"].get("id")) is int
                and reviewer["reviewer"]["id"] > 0
            ]
            if valid:
                return {"provider": provider, "model": model, "max_tokens": tokens, "authorization_ref": authorization}
    raise ValueError("required reviewers and prevention of self-review must be configured")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("environment_file", type=Path)
    parser.add_argument("--runs-file", type=Path, help="this workflow's runs created today (GitHub API JSON)")
    parser.add_argument("--governance-dir", type=Path, default=Path("governance"))
    args = parser.parse_args()
    try:
        order_file = args.governance_dir / "live_standing_order.json"
        order = json.loads(order_file.read_text()) if order_file.exists() else None
        runs_today = None
        if args.runs_file is not None:
            this_run = int(os.environ["GITHUB_RUN_ID"])
            listing = json.loads(args.runs_file.read_text())
            runs = listing.get("workflow_runs", [])
            if listing.get("total_count", 0) > len(runs):
                raise ValueError("run listing is paginated; cannot count today's runs exactly")
            runs_today = sum(1 for r in runs if r.get("id") != this_run and r.get("conclusion") != "cancelled")
        approved = authorize_dispatch(
            json.loads(Path(os.environ["GITHUB_EVENT_PATH"]).read_text()),
            os.environ["GITHUB_EVENT_NAME"],
            os.environ["GITHUB_REF"],
            os.environ["GITHUB_SHA"],
            json.loads(args.environment_file.read_text()),
            order,
            runs_today,
        )
    except (KeyError, OSError, ValueError, TypeError) as exc:
        raise SystemExit(f"Live inference refused: {exc}") from exc
    print(json.dumps(approved, sort_keys=True))


if __name__ == "__main__":
    main()
