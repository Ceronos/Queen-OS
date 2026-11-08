"""QOS-0008 portable JSON-output contract, version 1; never repairs model text."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

import jsonschema

from queen_os.serial.afser import sha256_hex
from queen_os.serial.jcs import canonicalize

SCHEMA_LIMIT = 16_384
FORMAT_NAME = "queen_output_v1"


class StructuredOutputError(ValueError):
    """Static failure codes, without copying response text into the error."""


def _pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in items:
        if key in out:
            raise StructuredOutputError("duplicate_json_key")
        out[key] = value
    return out


def _constant(_: str) -> Any:
    raise StructuredOutputError("nonfinite_json")


def strict_json(raw: str | bytes) -> Any:
    try:
        return json.loads(raw, object_pairs_hook=_pairs, parse_constant=_constant)
    except (ValueError, UnicodeError, RecursionError) as exc:
        raise StructuredOutputError("invalid_or_ambiguous_json") from exc


def _profile(node: Any, depth: int = 0) -> None:
    allowed = {"type", "properties", "required", "additionalProperties", "items", "enum", "description"}
    if depth > 8 or not isinstance(node, dict) or set(node) - allowed:
        raise StructuredOutputError("unsupported_schema_profile")
    types = node.get("type")
    types = [types] if isinstance(types, str) else types
    if not isinstance(types, list) or not types or any(not isinstance(t, str) for t in types):
        raise StructuredOutputError("explicit_schema_type_required")
    if len(set(types)) != len(types) or len(types) > 2 or (len(types) == 2 and "null" not in types):
        raise StructuredOutputError("unsupported_type_union")
    if set(types) - {"object", "array", "string", "integer", "number", "boolean", "null"}:
        raise StructuredOutputError("unsupported_schema_type")
    if "object" in types:
        props, required = node.get("properties"), node.get("required")
        if (
            not isinstance(props, dict)
            or len(props) > 64
            or not isinstance(required, list)
            or any(not isinstance(k, str) for k in required)
            or len(required) != len(set(required))
            or set(required) != set(props)
            or node.get("additionalProperties") is not False
        ):
            raise StructuredOutputError("closed_required_object_required")
        for child in props.values():
            _profile(child, depth + 1)
    elif {"properties", "required", "additionalProperties"} & set(node):
        raise StructuredOutputError("misplaced_object_keywords")
    if "array" in types:
        _profile(node.get("items"), depth + 1)
    elif "items" in node:
        raise StructuredOutputError("misplaced_array_keywords")
    if "enum" in node and (
        not isinstance(node["enum"], list)
        or not 1 <= len(node["enum"]) <= 64
        or any(isinstance(x, (dict, list)) for x in node["enum"])
    ):
        raise StructuredOutputError("primitive_enum_required")


@dataclass(frozen=True, init=False)
class JsonSchemaOutput:
    """Immutable snapshot, not an alias to a caller's mutable schema dictionary."""

    schema_bytes: bytes

    def __init__(self, schema: dict[str, Any]) -> None:
        try:
            raw = canonicalize(schema)
            if len(raw) > SCHEMA_LIMIT:
                raise StructuredOutputError("schema_size_limit")
            value = strict_json(raw)
            if value.get("type") != "object":
                raise StructuredOutputError("object_root_required")
            _profile(value)
            jsonschema.Draft202012Validator.check_schema(value)
        except (ValueError, TypeError, AttributeError, RecursionError, jsonschema.SchemaError) as exc:
            raise StructuredOutputError("invalid_or_unsupported_schema") from exc
        object.__setattr__(self, "schema_bytes", raw)

    @property
    def schema(self) -> dict[str, Any]:
        return dict(strict_json(self.schema_bytes))

    @property
    def sha256(self) -> str:
        return sha256_hex(self.schema_bytes)

    def validate(self, text: str) -> dict[str, Any]:
        value = strict_json(text)
        try:
            canonicalize(value)  # reject overflow/non-NFC/surrogates without rewriting
            if not isinstance(value, dict) or list(jsonschema.Draft202012Validator(self.schema).iter_errors(value)):
                raise StructuredOutputError("output_schema_mismatch")
        except (ValueError, TypeError, RecursionError) as exc:
            raise StructuredOutputError("invalid_or_schema_mismatched_output") from exc
        return value


def has_output_mode(codec: str, request: dict[str, Any]) -> bool:
    key = {
        "anthropic": "output_config",
        "openai": "response_format",
        "ollama": "format",
        "gemini": "generationConfig",
        "fixture": "output_schema",
    }.get(codec)
    if codec == "gemini":
        config = request.get("generationConfig") or {}
        return isinstance(config, dict) and bool(
            {"responseJsonSchema", "responseSchema", "responseMimeType"} & set(config)
        )
    return key is not None and key in request


def request_schema(codec: str, raw: bytes) -> JsonSchemaOutput:
    """Re-derive the promised schema from the exact outbound request, not a receipt label."""
    try:
        body = strict_json(raw)
        if codec == "anthropic":
            mode = body["output_config"]["format"]
            if set(mode) != {"type", "schema"} or mode["type"] != "json_schema":
                raise StructuredOutputError("invalid_output_mode")
            schema = mode["schema"]
        elif codec == "openai":
            mode = body["response_format"]
            spec = mode["json_schema"]
            if (
                set(mode) != {"type", "json_schema"}
                or mode["type"] != "json_schema"
                or set(spec) != {"name", "strict", "schema"}
                or spec["strict"] is not True
                or spec["name"] != FORMAT_NAME
            ):
                raise StructuredOutputError("invalid_output_mode")
            schema = spec["schema"]
        elif codec == "gemini":
            config = body["generationConfig"]
            if config["responseMimeType"] != "application/json" or "responseSchema" in config:
                raise StructuredOutputError("invalid_output_mode")
            schema = config["responseJsonSchema"]
        elif codec == "ollama":
            if body.get("stream") is not False:
                raise StructuredOutputError("streaming_not_supported")
            schema = body["format"]
        elif codec == "fixture":
            schema = body["output_schema"]
        else:
            raise StructuredOutputError("unsupported_structured_codec")
        if codec == "openai" and body.get("stream") is not False:
            raise StructuredOutputError("streaming_not_supported")
        return JsonSchemaOutput(schema)
    except (KeyError, TypeError, AttributeError, ValueError, RecursionError) as exc:
        raise StructuredOutputError("invalid_structured_request") from exc


def response_fields(codec: str, raw: bytes) -> dict[str, Any]:
    """Version-1 structured response decoder. Legacy text decoders are unchanged."""
    try:
        data = strict_json(raw)
        if not isinstance(data, dict) or "error" in data:
            raise StructuredOutputError("invalid_response_envelope")
        if codec == "anthropic":
            blocks = data["content"]
            if data["stop_reason"] != "end_turn" or len(blocks) != 1 or blocks[0]["type"] != "text":
                raise StructuredOutputError("incomplete_refused_or_nontext_response")
            text, finish = blocks[0]["text"], data["stop_reason"]
            usage = data.get("usage") or {}
            model, inputs, outputs = data.get("model"), usage.get("input_tokens"), usage.get("output_tokens")
        elif codec == "openai":
            choices = data["choices"]
            if len(choices) != 1 or choices[0]["finish_reason"] != "stop":
                raise StructuredOutputError("incomplete_or_multiple_candidates")
            message = choices[0]["message"]
            if message.get("refusal") or message.get("tool_calls") or message.get("function_call"):
                raise StructuredOutputError("refusal_or_tool_output")
            text, finish = message["content"], choices[0]["finish_reason"]
            usage = data.get("usage") or {}
            model, inputs, outputs = data.get("model"), usage.get("prompt_tokens"), usage.get("completion_tokens")
        elif codec == "gemini":
            candidates = data["candidates"]
            if (
                len(candidates) != 1
                or candidates[0]["finishReason"] != "STOP"
                or (data.get("promptFeedback") or {}).get("blockReason")
            ):
                raise StructuredOutputError("blocked_incomplete_or_multiple_candidates")
            parts = candidates[0]["content"]["parts"]
            if len(parts) != 1 or parts[0].get("thought") or set(parts[0]) != {"text"}:
                raise StructuredOutputError("nontext_or_multiple_parts")
            text, finish = parts[0]["text"], candidates[0]["finishReason"]
            usage = data.get("usageMetadata") or {}
            model = data.get("modelVersion")
            inputs, outputs = usage.get("promptTokenCount"), usage.get("candidatesTokenCount")
        elif codec == "ollama":
            message = data["message"]
            if data.get("done") is not True or data["done_reason"] != "stop" or message.get("tool_calls"):
                raise StructuredOutputError("incomplete_or_tool_output")
            text, finish = message["content"], data["done_reason"]
            model, inputs, outputs = data.get("model"), data.get("prompt_eval_count"), data.get("eval_count")
        elif codec == "fixture":
            text, finish, model, inputs, outputs = data["text"], "fixture", data["model"], None, None
        else:
            raise StructuredOutputError("unsupported_structured_codec")
        if not isinstance(text, str) or (model is not None and not isinstance(model, str)):
            raise StructuredOutputError("invalid_response_types")
        if any(x is not None and (type(x) is not int or x < 0) for x in [inputs, outputs]):
            raise StructuredOutputError("invalid_token_counts")
        return {
            "text": text,
            "finish_reason": finish,
            "model_reported": model,
            "input_tokens": inputs,
            "output_tokens": outputs,
        }
    except (KeyError, IndexError, TypeError, AttributeError, ValueError, RecursionError) as exc:
        raise StructuredOutputError("invalid_structured_response") from exc
