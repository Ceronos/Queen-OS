"""Fail-closed admission for the separate, manually dispatched live CI workflow.

This verifies workflow intent and environment configuration, not containment or
the truth of the human authorization record. It never contacts a model or keyring.
"""

from __future__ import annotations

import argparse
import json
import os
import re
from pathlib import Path
from typing import Any


def authorize_dispatch(
    event: dict[str, Any], event_name: str, ref: str, sha: str, environment: dict[str, Any]
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
    if not isinstance(authorization, str) or re.fullmatch(r"https://[^\s]{1,2000}", authorization) is None:
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
    args = parser.parse_args()
    try:
        approved = authorize_dispatch(
            json.loads(Path(os.environ["GITHUB_EVENT_PATH"]).read_text()),
            os.environ["GITHUB_EVENT_NAME"],
            os.environ["GITHUB_REF"],
            os.environ["GITHUB_SHA"],
            json.loads(args.environment_file.read_text()),
        )
    except (KeyError, OSError, ValueError, TypeError) as exc:
        raise SystemExit(f"Live inference refused: {exc}") from exc
    print(json.dumps(approved, sort_keys=True))


if __name__ == "__main__":
    main()
