"""Offline schema/wire/custody/replay tests. Every inference receipt is fixture-marked."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import httpx
import pytest

from queen_os.authority import Grant
from queen_os.gate.gate import Gate
from queen_os.hive import Hive
from queen_os.providers import FixtureProvider, InferenceRequest, JsonSchemaOutput, Message, ProviderError
from queen_os.providers.adapters import AnthropicProvider, GeminiProvider, OllamaProvider, OpenAICompatibleProvider
from queen_os.providers.receipt import Inference, NonSimulationViolation, StructuredOutputRejected, verify_receipt
from queen_os.providers.structured import StructuredOutputError, request_schema, response_fields, strict_json
from queen_os.queen.egg import lay
from queen_os.secrets import Secret
from queen_os.serial import canonicalize
from queen_os.workers.claim import Worker

SCHEMA = {
    "type": "object",
    "properties": {"answer": {"type": "string"}},
    "required": ["answer"],
    "additionalProperties": False,
}
OUTPUT = JsonSchemaOutput(SCHEMA)
REQ = InferenceRequest("m", (Message("user", "return JSON"),), max_tokens=64, output=OUTPUT)
KEY = Secret("fixture-credential-never-live-000000")


@pytest.fixture
def hive(tmp_path: Path):  # type: ignore[no-untyped-def]
    with Hive.init(tmp_path / "h", "structured", mode="test") as h:
        yield h


def grant(hive: Hive):  # type: ignore[no-untyped-def]
    return hive.authority().issue("w", "test", Grant(providers=("*",), models=("m",), max_calls=1), 60_000)


def provider(codec: str):  # type: ignore[no-untyped-def]
    if codec == "anthropic":
        p = AnthropicProvider(KEY)
    elif codec == "gemini":
        p = GeminiProvider(KEY)
    elif codec == "ollama":
        p = OllamaProvider()
    else:
        p = OpenAICompatibleProvider("openai", "https://fixture.invalid/v1", KEY, supports_structured_output=True)
    p.kind = "fixture"  # explicit signed classification: mocked HTTP is never real-provider evidence
    return p


def envelope(codec: str, text: str = '{"answer":"bee"}') -> dict[str, Any]:
    if codec == "anthropic":
        return {"content": [{"type": "text", "text": text}], "stop_reason": "end_turn", "model": "m"}
    if codec == "gemini":
        return {"candidates": [{"content": {"parts": [{"text": text}]}, "finishReason": "STOP"}], "modelVersion": "m"}
    if codec == "ollama":
        return {"message": {"content": text}, "done": True, "done_reason": "stop", "model": "m"}
    return {"choices": [{"message": {"content": text}, "finish_reason": "stop"}], "model": "m"}


def test_schema_is_snapshotted_not_mutably_aliased() -> None:
    original = copy.deepcopy(SCHEMA)
    spec = JsonSchemaOutput(original)
    original["properties"]["answer"]["type"] = "integer"
    exposed = spec.schema
    exposed["properties"].clear()
    assert spec.schema == SCHEMA and spec.sha256 == OUTPUT.sha256
    assert spec.validate(' {"answer": "bee"} ') == {"answer": "bee"}


@pytest.mark.parametrize(
    "change",
    [
        {"$ref": "https://forbidden.invalid/schema"},
        {"default": {}},
        {"type": "array"},
        {"additionalProperties": True},
        {"required": []},
        {"type": ["object", "string"]},
        {"description": "x" * 17_000},
    ],
)
def test_unsupported_schema_is_rejected_without_network(change: dict[str, Any]) -> None:
    with pytest.raises(StructuredOutputError):
        JsonSchemaOutput({**SCHEMA, **change})


@pytest.mark.parametrize(
    "text",
    [
        '{"answer":1}',
        '{"answer":"x","answer":"y"}',
        '{"answer":NaN}',
        '{"answer":1e400}',
        '```json\n{"answer":"bee"}\n```',
        '{"answer":',
        '{"answer":"bee","extra":1}',
    ],
)
def test_invalid_structured_text_retains_signed_failure_and_consumes_once(hive: Hive, text: str) -> None:
    cap = grant(hive)
    p = FixtureProvider("scripted", [text, '{"answer":"bee"}'])
    with pytest.raises(StructuredOutputRejected) as error:
        Inference(hive).run(p, REQ, actor="w", capability=cap)
    receipt = error.value.receipt
    assert receipt.payload["v"] == 2 and receipt.payload["provider_kind"] == "fixture"
    assert receipt.payload["completion_sha"] is None
    assert receipt.payload["structured_output"]["valid"] is False
    assert json.loads(hive.blobs.get(receipt.payload["response_sha"]))["text"] == text
    assert p._replies == ['{"answer":"bee"}']  # no implicit retry
    assert hive.ledger.verify_chain(require_signatures=True) == 4
    with pytest.raises(NonSimulationViolation):
        verify_receipt(hive, receipt)
    with pytest.raises(PermissionError):
        Inference(hive).run(p, REQ, actor="w", capability=cap)
    assert p._replies == ['{"answer":"bee"}']


@pytest.mark.parametrize("codec", ["anthropic", "openai", "gemini", "ollama"])
def test_native_wire_modes_and_reopen_replay(hive: Hive, codec: str) -> None:
    p = provider(codec)
    call = p.encode(REQ)
    body = json.loads(call.body)
    if codec == "anthropic":
        assert body["output_config"] == {"format": {"type": "json_schema", "schema": SCHEMA}}
    elif codec == "openai":
        assert body["response_format"] == {
            "type": "json_schema",
            "json_schema": {"name": "queen_output_v1", "strict": True, "schema": SCHEMA},
        }
    elif codec == "gemini":
        assert body["generationConfig"]["responseMimeType"] == "application/json"
        assert body["generationConfig"]["responseJsonSchema"] == SCHEMA
    else:
        assert body["format"] == SCHEMA and body["stream"] is False
    assert request_schema(codec, call.body).schema_bytes == OUTPUT.schema_bytes
    assert "tools" not in body and "tool_choice" not in body
    assert KEY.reveal().encode() not in call.body
    captured = []
    raw = json.dumps(envelope(codec)).encode()

    def respond(request: httpx.Request) -> httpx.Response:
        captured.append(request.content)
        return httpx.Response(200, content=raw)

    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        w = Inference(hive, client).run(p, REQ, actor="w", capability=grant(hive))
    assert len(captured) == 1 and captured[0] == hive.blobs.get(w.receipt.payload["request_sha"])
    assert hive.blobs.get(w.receipt.payload["response_sha"]) == raw
    assert verify_receipt(hive, w.receipt).text == '{"answer":"bee"}'
    root, seq = hive.root, w.receipt.seq
    hive.close()
    with Hive.open(root) as reopened:
        event = reopened.ledger.get(seq)
        assert event is not None
        assert verify_receipt(reopened, event).text == w.result.text
        assert reopened.ledger.verify_chain(require_signatures=True) == 4


@pytest.mark.parametrize("codec", ["anthropic", "openai", "gemini", "ollama"])
def test_truncated_or_refused_envelope_cannot_pass_even_with_valid_json(hive: Hive, codec: str) -> None:
    p = provider(codec)
    data = envelope(codec)
    if codec == "anthropic":
        data["stop_reason"] = "max_tokens"
    elif codec == "openai":
        data["choices"][0]["finish_reason"] = "length"
    elif codec == "gemini":
        data["candidates"][0]["finishReason"] = "SAFETY"
    else:
        data["done"] = False
    raw = json.dumps(data).encode()
    with (
        httpx.Client(transport=httpx.MockTransport(lambda _: httpx.Response(200, content=raw))) as client,
        pytest.raises(StructuredOutputRejected) as error,
    ):
        Inference(hive, client).run(p, REQ, actor="w", capability=grant(hive))
    assert hive.blobs.get(error.value.receipt.payload["response_sha"]) == raw
    with pytest.raises(NonSimulationViolation):
        verify_receipt(hive, error.value.receipt)


@pytest.mark.parametrize("raw", [b"not-json", b'{"text":"x","text":"y"}', b'{"text":NaN}', b"[]"])
def test_malformed_http_success_is_retained(hive: Hive, raw: bytes) -> None:
    p = provider("openai")
    with (
        httpx.Client(transport=httpx.MockTransport(lambda _: httpx.Response(200, content=raw))) as client,
        pytest.raises(StructuredOutputRejected) as error,
    ):
        Inference(hive, client).run(p, REQ, actor="w", capability=grant(hive))
    assert hive.blobs.get(error.value.receipt.payload["response_sha"]) == raw


def test_unconfirmed_compatible_mode_and_ollama_cloud_fail_before_spend(hive: Hive) -> None:
    cap = grant(hive)
    for p in [
        OpenAICompatibleProvider("unknown", "http://fixture.invalid", None),
        OllamaProvider("https://ollama.com"),
    ]:
        with pytest.raises(ProviderError):
            Inference(hive).run(p, REQ, actor="w", capability=cap)
    assert [e.kind for e in hive.ledger.events()] == ["hive.genesis", "capability.issued"]


@pytest.mark.parametrize("mutation", ["schema", "wire", "valid", "version", "decoder", "downgrade"])
def test_forged_structured_metadata_cannot_verify(hive: Hive, mutation: str) -> None:
    w = Inference(hive).run(FixtureProvider("s", ['{"answer":"bee"}']), REQ, actor="w", capability=grant(hive))
    p = copy.deepcopy(w.receipt.payload)
    if mutation == "schema":
        other = JsonSchemaOutput({**SCHEMA, "properties": {"answer": {"type": "integer"}}})
        p["structured_output"]["schema_sha"] = hive.blobs.put(other.schema_bytes)
    elif mutation == "wire":
        p["request_sha"] = hive.blobs.put(b'{"model":"m","messages":["x"]}')
    elif mutation == "valid":
        p["structured_output"]["valid"] = 1
    elif mutation == "version":
        p["v"] = 99
    elif mutation == "decoder":
        p["structured_output"]["decoder_v"] = 99
    else:
        p["v"] = 1
        p.pop("structured_output")
    forged = hive.ledger.append("inference.receipt", "w", p)
    with pytest.raises(NonSimulationViolation):
        verify_receipt(hive, forged)


def test_v2_receipt_hatches_without_changing_completion_bytes(hive: Hive) -> None:
    egg = lay(hive, "g", "diploid", {"q": "fixture JSON"}, SCHEMA, stimulus=0.9)
    worker = Worker(hive, "a", providers=("scripted",), models=("m",))
    claim = worker.claim()
    assert claim is not None
    text = ' { "answer" : "bee" } '
    w = Inference(hive).run(FixtureProvider("scripted", [text]), REQ, actor=worker.actor, capability=claim.capability)
    assert w.result.text == text and verify_receipt(hive, w.receipt).text == text
    worker.deliver(claim, OUTPUT.validate(w.result.text))
    assert Gate(hive).review(egg.egg_id).verdict == "hatched"


def test_rejected_structured_receipt_cannot_back_a_delivery(hive: Hive) -> None:
    egg = lay(hive, "g", "diploid", {"q": "fixture JSON"}, SCHEMA, stimulus=0.9)
    worker = Worker(hive, "a", providers=("scripted",), models=("m",))
    claim = worker.claim()
    assert claim is not None
    with pytest.raises(StructuredOutputRejected):
        Inference(hive).run(
            FixtureProvider("scripted", ['{"answer":true}']), REQ, actor=worker.actor, capability=claim.capability
        )
    worker.deliver(claim, {"answer": "bee"})
    assert Gate(hive).review(egg.egg_id).verdict == "purged"


def test_cli_schema_success_and_failure_have_distinct_status(
    hive: Hive, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    import queen_os.providers
    from queen_os.cli import main

    p = tmp_path / "schema.json"
    p.write_bytes(canonicalize(SCHEMA))
    monkeypatch.setattr(queen_os.providers, "build", lambda *args: FixtureProvider("scripted", ['{"answer":"bee"}']))
    args = ["infer", "scripted", "m", "fixture", "--hive", str(hive.root), "--json-schema", str(p)]
    assert main(args) == 0 and "bee" in capsys.readouterr().out
    monkeypatch.setattr(queen_os.providers, "build", lambda *args: FixtureProvider("scripted", ['{"answer":true}']))
    assert main(args) == 4 and "evidence retained" in capsys.readouterr().err


def test_strict_response_rejects_tool_or_refusal_with_valid_content() -> None:
    data = envelope("openai")
    data["choices"][0]["message"]["tool_calls"] = [{"function": {"name": "shell", "arguments": "{}"}}]
    with pytest.raises(StructuredOutputError):
        response_fields("openai", json.dumps(data).encode())
    data = envelope("openai")
    data["choices"][0]["message"]["refusal"] = "refused"
    with pytest.raises(StructuredOutputError):
        response_fields("openai", json.dumps(data).encode())
    with pytest.raises(StructuredOutputError):
        strict_json('{"a":1,"\\u0061":2}')


@pytest.mark.parametrize("codec", ["anthropic", "openai", "gemini", "ollama"])
def test_missing_or_weakened_native_wire_schema_is_rejected(codec: str) -> None:
    body = json.loads(provider(codec).encode(REQ).body)
    if codec == "anthropic":
        body["output_config"]["format"]["type"] = "text"
    elif codec == "openai":
        body["response_format"]["json_schema"]["strict"] = False
    elif codec == "gemini":
        body["generationConfig"]["responseMimeType"] = "text/plain"
    else:
        body["format"] = "json"  # syntax-only mode is not a schema contract
    with pytest.raises(StructuredOutputError):
        request_schema(codec, json.dumps(body).encode())


@pytest.mark.parametrize("status", [302, 400, 429, 500])
def test_http_error_even_with_valid_body_is_retained_but_never_accepted(hive: Hive, status: int) -> None:
    raw = json.dumps(envelope("openai")).encode()
    with (
        httpx.Client(transport=httpx.MockTransport(lambda _: httpx.Response(status, content=raw))) as client,
        pytest.raises(StructuredOutputRejected) as error,
    ):
        Inference(hive, client).run(provider("openai"), REQ, actor="w", capability=grant(hive))
    event = error.value.receipt
    assert event.payload["http_status"] == status
    assert hive.blobs.get(event.payload["response_sha"]) == raw
    with pytest.raises(NonSimulationViolation):
        verify_receipt(hive, event)


def test_invalid_structured_receipt_cannot_be_forged_valid(hive: Hive) -> None:
    with pytest.raises(StructuredOutputRejected) as error:
        Inference(hive).run(FixtureProvider("s", ['{"answer":true}']), REQ, actor="w", capability=grant(hive))
    payload = copy.deepcopy(error.value.receipt.payload)
    payload["structured_output"].update(valid=True, failure=None)
    event = hive.ledger.append("inference.receipt", "w", payload)
    with pytest.raises(NonSimulationViolation):
        verify_receipt(hive, event)


def test_structured_fixture_still_refused_before_production_spend(tmp_path: Path) -> None:
    with Hive.init(tmp_path / "prod", "prod") as h:
        p = FixtureProvider("s", ['{"answer":"bee"}'])
        with pytest.raises(NonSimulationViolation):
            Inference(h).run(p, REQ, actor="w", capability=grant(h))
        assert p._replies == ['{"answer":"bee"}']
        assert len(list(h.ledger.events())) == 2


def test_schema_nested_nullable_array_and_enum() -> None:
    schema = {
        **SCHEMA,
        "properties": {"answer": {"type": "array", "items": {"type": ["string", "null"], "enum": ["bee", None]}}},
    }
    spec = JsonSchemaOutput(schema)
    assert spec.validate('{"answer":["bee",null]}') == {"answer": ["bee", None]}
    with pytest.raises(StructuredOutputError):
        spec.validate('{"answer":["wasp"]}')
