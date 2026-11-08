"""Explicit operator-only LM Studio lifecycle; no downloads, generation or retries."""

from __future__ import annotations

import ipaddress
import re
import unicodedata
from typing import Any
from urllib.parse import urlsplit

import httpx

from queen_os.hive import Hive
from queen_os.providers.structured import strict_json

MAX_RESPONSE_BYTES = 1024 * 1024
MAX_CONTEXT = 32768


class LocalModelError(ValueError):
    """Static failure reason; never echo raw server bodies or credentials."""


def local_root(url: str) -> str:
    try:
        if any(ord(c) < 32 or ord(c) == 127 for c in url):
            raise LocalModelError("invalid_local_server_url")
        parsed = urlsplit(url)
        host = parsed.hostname or ""
        if host == "localhost":
            host = "127.0.0.1"  # no DNS or proxy routing for lifecycle effects
        if (
            parsed.scheme != "http"
            or not ipaddress.ip_address(host).is_loopback
            or parsed.username is not None
            or parsed.password is not None
            or parsed.query
            or parsed.fragment
            or parsed.path not in {"", "/", "/v1", "/v1/"}
        ):
            raise LocalModelError("loopback_http_server_required")
        port = 1234 if parsed.port is None else parsed.port
        if not 1 <= port <= 65535:
            raise LocalModelError("invalid_port")
        return f"http://[{host}]:{port}" if ":" in host else f"http://{host}:{port}"
    except ValueError as exc:
        raise LocalModelError("invalid_local_server_url") from exc


def _identifier(value: Any) -> str:
    if not isinstance(value, str):
        raise LocalModelError("invalid_model_identifier")
    try:
        encoded = value.encode("utf-8")
    except UnicodeError as exc:
        raise LocalModelError("invalid_model_identifier") from exc
    if not 1 <= len(encoded) <= 512 or unicodedata.normalize("NFC", value) != value:
        raise LocalModelError("invalid_model_identifier")
    if any(ord(c) < 32 or ord(c) == 127 for c in value):
        raise LocalModelError("invalid_model_identifier")
    return value


def _integer(value: Any, maximum: int) -> int:
    if type(value) is not int or not 1 <= value <= maximum:
        raise LocalModelError("invalid_resource_bound")
    return int(value)


class LMStudio:
    """Native REST v1 lifecycle, independent of the existing witnessed inference adapter.

    Injected transports are always fixture-classified and refused for production effects.
    The default transport disables environment proxies and redirects. No token discovery.
    """

    def __init__(self, base_url: str = "http://127.0.0.1:1234", *, transport: httpx.BaseTransport | None = None):
        self.root = local_root(base_url)
        self.fixture = transport is not None
        self._transport = transport

    def _request(self, method: str, path: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
        try:
            with (
                httpx.Client(
                    transport=self._transport, trust_env=False, follow_redirects=False, timeout=180.0
                ) as client,
                client.stream(method, self.root + path, json=body) as response,
            ):
                if response.status_code != 200:
                    raise LocalModelError("local_server_non_success")
                raw = bytearray()
                for chunk in response.iter_bytes(chunk_size=65536):
                    raw.extend(chunk)
                    if len(raw) > MAX_RESPONSE_BYTES:
                        raise LocalModelError("local_response_size_limit")
            value = strict_json(bytes(raw))
            if not isinstance(value, dict):
                raise LocalModelError("invalid_local_response")
            return value
        except (httpx.HTTPError, ValueError, UnicodeError) as exc:
            raise LocalModelError("local_request_or_response_failed") from exc

    def models(self) -> list[dict[str, Any]]:
        """Bounded normalized LLM inventory; no load, inference or automatic download."""
        value = self._request("GET", "/api/v1/models").get("models")
        if not isinstance(value, list) or len(value) > 256:
            raise LocalModelError("invalid_model_inventory")
        models: list[dict[str, Any]] = []
        keys: set[str] = set()
        ids: set[str] = set()
        for item in value:
            if not isinstance(item, dict) or item.get("type") not in ("llm", "embedding", "decision"):
                raise LocalModelError("invalid_model_inventory")
            if item["type"] != "llm":
                continue
            key = _identifier(item.get("key"))
            size = _integer(item.get("size_bytes"), 1024**4)
            maximum = item.get("max_context_length")
            if maximum is not None:
                maximum = _integer(maximum, 10_000_000)
            loaded = item.get("loaded_instances")
            if key in keys or not isinstance(loaded, list) or len(loaded) > 32:
                raise LocalModelError("ambiguous_model_inventory")
            keys.add(key)
            instances = []
            for instance in loaded:
                if not isinstance(instance, dict) or not isinstance(instance.get("config"), dict):
                    raise LocalModelError("invalid_loaded_instance")
                instance_id = _identifier(instance.get("id"))
                context = _integer(instance["config"].get("context_length"), 10_000_000)
                if instance_id in ids:
                    raise LocalModelError("ambiguous_instance_id")
                ids.add(instance_id)
                instances.append({"id": instance_id, "context_length": context})
            models.append({"key": key, "size_bytes": size, "max_context_length": maximum, "instances": instances})
        return models

    def change(
        self,
        hive: Hive,
        operation_id: str,
        action: str,
        target: str,
        *,
        context_length: int = 2048,
        max_weights_bytes: int = 16 * 1024**3,
    ) -> dict[str, Any]:
        """One explicit load/unload POST after a signed intent. Repeated IDs never POST."""
        if not re.fullmatch(r"[A-Za-z0-9_.:-]{1,96}", operation_id) or action not in {"load", "unload"}:
            raise LocalModelError("invalid_lifecycle_operation")
        _identifier(target)
        if self.fixture and hive.mode != "test":
            raise LocalModelError("fixture_lifecycle_refused_in_production")
        hive.ledger.verify_chain(require_signatures=True)
        if hive.ledger.find_op(f"local-model:{operation_id}:intent") is not None:
            raise LocalModelError("operation_already_recorded_use_status_no_retry")
        context_length = _integer(context_length, MAX_CONTEXT)
        max_weights_bytes = _integer(max_weights_bytes, 256 * 1024**3)
        inventory = self.models()
        model: dict[str, Any] | None = None
        for candidate in inventory:
            if action == "load" and candidate["key"] == target:
                model = candidate
            if action == "unload" and any(i["id"] == target for i in candidate["instances"]):
                model = candidate
        if model is None:
            raise LocalModelError("exact_installed_model_or_instance_required")
        if action == "load" and (
            model["instances"]
            or model["size_bytes"] > max_weights_bytes
            or model["max_context_length"] is None
            or context_length > model["max_context_length"]
        ):
            raise LocalModelError("model_loaded_or_resource_bound_refused")
        payload = {
            "v": 1,
            "operation_id": operation_id,
            "action": action,
            "target": target,
            "model_key": model["key"],
            "server": self.root,
            "context_length": context_length if action == "load" else None,
            "max_weights_bytes": max_weights_bytes,
            "reported_weight_bytes": model["size_bytes"],
            "fixture": self.fixture,
        }
        # Serialize only intent creation. No database lock is held across network effects.
        with hive.ledger.transaction() as db:
            if hive.ledger.find_op(f"local-model:{operation_id}:intent") is not None:
                raise LocalModelError("operation_already_recorded_use_status_no_retry")
            seq = hive.ledger.append_locked(
                db, "local_model.intent", "operator:cli", payload, op_id=f"local-model:{operation_id}:intent"
            )
        hive.ledger._post_write_fetch(seq)
        body: dict[str, Any] = (
            {"model": target, "context_length": context_length, "echo_load_config": True}
            if action == "load"
            else {"instance_id": target}
        )
        try:
            response = self._request("POST", f"/api/v1/models/{action}", body)
            instance_id = _identifier(response.get("instance_id"))
            if action == "unload" and instance_id != target:
                raise LocalModelError("unload_instance_mismatch")
            if action == "load" and (
                response.get("type") != "llm"
                or response.get("status") != "loaded"
                or not isinstance(response.get("load_config"), dict)
                or type(response["load_config"].get("context_length")) is not int
                or response["load_config"]["context_length"] != context_length
            ):
                raise LocalModelError("load_response_configuration_mismatch")
            hive.ledger.append(
                "local_model.response",
                "operator:cli",
                {"operation_id": operation_id, "instance_id": instance_id, "fixture": self.fixture},
                op_id=f"local-model:{operation_id}:response",
            )
            observed = self.status(hive, operation_id)
            if not observed["desired_state_observed"]:
                raise LocalModelError("lifecycle_state_not_observed")
            return observed
        except LocalModelError as exc:
            hive.ledger.append(
                "local_model.unknown",
                "operator:cli",
                {"operation_id": operation_id, "status": "UNKNOWN", "fixture": self.fixture},
            )
            raise LocalModelError("effect_unknown_use_status_no_retry") from exc

    def status(self, hive: Hive, operation_id: str) -> dict[str, Any]:
        """Reconcile current target state by GET only. Never repeat an earlier POST."""
        hive.ledger.verify_chain(require_signatures=True)
        intent = hive.ledger.find_op(f"local-model:{operation_id}:intent")
        if intent is None or intent.kind != "local_model.intent":
            raise LocalModelError("unknown_lifecycle_operation")
        p = intent.payload
        if p["server"] != self.root or p["fixture"] != self.fixture:
            raise LocalModelError("lifecycle_provenance_mismatch")
        inventory = self.models()
        response = hive.ledger.find_op(f"local-model:{operation_id}:response")
        expected_id = None if response is None else response.payload["instance_id"]
        matching = [
            i
            for m in inventory
            if m["key"] == p["model_key"]
            for i in m["instances"]
            if i["context_length"] == p["context_length"] and (expected_id is None or i["id"] == expected_id)
        ]
        present_ids = {i["id"] for m in inventory for i in m["instances"]}
        observed = len(matching) == 1 if p["action"] == "load" else p["target"] not in present_ids
        result = {
            "operation_id": operation_id,
            "action": p["action"],
            "model_key": p["model_key"],
            "desired_state_observed": observed,
            "instance_id": (matching[0]["id"] if observed else None) if p["action"] == "load" else p["target"],
            "context_length": p["context_length"],
            "status": "PRODUCER_STATE_OBSERVED" if observed else "UNKNOWN",
            "causality": "not_established_by_readback",
            "fixture": self.fixture,
        }
        hive.ledger.append("local_model.observation", "operator:cli", result)
        return result
