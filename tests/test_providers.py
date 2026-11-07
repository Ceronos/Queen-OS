"""Wire-codec tests. These check request encoding and response decoding against each
vendor's documented JSON shapes. They make no inference claims; live inference is
proven in tests/live/ against real endpoints.
"""

from __future__ import annotations

import json

import pytest

from queen_os.providers import PRESETS, InferenceRequest, Message, ProviderError, build, lineage_of
from queen_os.providers.adapters import AnthropicProvider, GeminiProvider, OllamaProvider, OpenAICompatibleProvider
from queen_os.secrets import Secret, SecretError, SecretStore

KEY = Secret("test-key-" + "x" * 24, "test")
REQ = InferenceRequest(
    "m-1",
    (Message("user", "hi"), Message("assistant", "yo"), Message("user", "go")),
    system="be terse",
    max_tokens=64,
    temperature=0.2,
)


def test_anthropic_codec() -> None:
    p = AnthropicProvider(KEY)
    call = p.encode(REQ)
    body = json.loads(call.body)
    assert call.url == "https://api.anthropic.com/v1/messages"
    assert call.headers["x-api-key"] == KEY.reveal() and call.headers["anthropic-version"] == "2023-06-01"
    assert body["system"] == "be terse" and body["max_tokens"] == 64 and len(body["messages"]) == 3
    assert KEY.reveal().encode() not in call.body
    raw = json.dumps(
        {
            "id": "msg_1",
            "type": "message",
            "role": "assistant",
            "model": "claude-x",
            "content": [
                {"type": "text", "text": "Hel"},
                {"type": "tool_use", "id": "t"},
                {"type": "text", "text": "lo"},
            ],
            "stop_reason": "end_turn",
            "usage": {"input_tokens": 9, "output_tokens": 2},
        }
    ).encode()
    r = p.decode(raw)
    assert (r.text, r.finish_reason, r.model_reported, r.input_tokens, r.output_tokens) == (
        "Hello",
        "end_turn",
        "claude-x",
        9,
        2,
    )
    with pytest.raises(ProviderError):
        p.decode(b'{"type":"error","error":{"type":"overloaded_error"}}')


def test_openai_compatible_codec_and_token_field() -> None:
    p = OpenAICompatibleProvider("openai", "https://api.openai.com/v1", KEY, max_tokens_field="max_completion_tokens")
    call = p.encode(REQ)
    body = json.loads(call.body)
    assert call.url.endswith("/chat/completions") and call.headers["authorization"] == f"Bearer {KEY.reveal()}"
    assert body["messages"][0] == {"role": "system", "content": "be terse"}
    assert body["max_completion_tokens"] == 64 and "max_tokens" not in body and body["stream"] is False
    raw = json.dumps(
        {
            "model": "gpt-x",
            "choices": [{"message": {"role": "assistant", "content": "ok"}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 5, "completion_tokens": 1},
        }
    ).encode()
    r = p.decode(raw)
    assert (r.text, r.finish_reason, r.input_tokens, r.output_tokens) == ("ok", "stop", 5, 1)
    with pytest.raises(ProviderError):
        p.decode(b'{"error":{"type":"invalid_request_error"}}')
    with pytest.raises(ProviderError):
        p.decode(b"<html>bad gateway</html>")


def test_local_openai_compatible_sends_no_auth_header() -> None:
    p = OpenAICompatibleProvider("lmstudio", "http://localhost:1234/v1", None, kind="local")
    assert "authorization" not in p.encode(REQ).headers


def test_gemini_codec_keeps_key_out_of_url() -> None:
    p = GeminiProvider(KEY)
    call = p.encode(REQ)
    body = json.loads(call.body)
    assert KEY.reveal() not in call.url and call.headers["x-goog-api-key"] == KEY.reveal()
    assert call.url.endswith("/v1beta/models/m-1:generateContent")
    assert [c["role"] for c in body["contents"]] == ["user", "model", "user"]
    assert body["systemInstruction"]["parts"][0]["text"] == "be terse"
    raw = json.dumps(
        {
            "candidates": [
                {"content": {"parts": [{"text": "hmm", "thought": True}, {"text": "done"}]}, "finishReason": "STOP"}
            ],
            "usageMetadata": {"promptTokenCount": 4, "candidatesTokenCount": 1},
            "modelVersion": "gemini-x",
        }
    ).encode()
    r = p.decode(raw)
    assert (r.text, r.finish_reason, r.model_reported) == ("done", "STOP", "gemini-x")
    with pytest.raises(ProviderError, match="SAFETY"):
        p.decode(b'{"promptFeedback":{"blockReason":"SAFETY"}}')


def test_ollama_codec() -> None:
    p = OllamaProvider()
    body = json.loads(p.encode(REQ).body)
    assert body["stream"] is False and body["options"] == {"num_predict": 64, "temperature": 0.2}
    r = p.decode(
        b'{"model":"qwen2.5:0.5b","message":{"role":"assistant","content":"pong"},"done":true,'
        b'"done_reason":"stop","prompt_eval_count":12,"eval_count":2}'
    )
    assert (r.text, r.input_tokens, r.output_tokens) == ("pong", 12, 2)


@pytest.mark.parametrize(
    ("model", "lineage"),
    [
        ("claude-opus-5-5", "anthropic"),
        ("anthropic/claude-sonnet-5-5", "anthropic"),
        ("gpt-5-mini", "openai"),
        ("o4-mini", "openai"),
        ("gemini-3-pro", "google"),
        ("gemma3:4b", "google"),
        ("qwen2.5:0.5b", "alibaba"),
        ("meta-llama/llama-4-scout", "meta"),
        ("deepseek-r2", "deepseek"),
        ("grok-5", "xai"),
        ("mixtral-8x22b", "mistral"),
        ("Hermes-4-405B", "nous"),
        ("mystery-7b", "unknown:mystery-7b"),
    ],
)
def test_lineage_is_by_model_family_not_host(model: str, lineage: str) -> None:
    assert lineage_of(model) == lineage


def test_registry_builds_every_preset(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:  # type: ignore[no-untyped-def]
    store = SecretStore(tmp_path)
    for name, preset in PRESETS.items():
        if preset.key_required:
            with pytest.raises(SecretError):
                build(name, store)
            monkeypatch.setenv(preset.key_env[0], "k-" + name)
        provider = build(name, store)
        assert provider.encode(REQ).url.startswith(("http://", "https://"))


def test_vendor_base_url_variables_are_not_inherited(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:  # type: ignore[no-untyped-def]
    """An IDE agent's ANTHROPIC_BASE_URL must not silently reroute a hive's inference."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "k")
    monkeypatch.setenv("ANTHROPIC_BASE_URL", "http://attacker.invalid")
    assert build("anthropic", SecretStore(tmp_path)).base_url == "https://api.anthropic.com"
    monkeypatch.setenv("QUEEN_ANTHROPIC_BASE_URL", "http://gateway.internal")
    assert build("anthropic", SecretStore(tmp_path)).base_url == "http://gateway.internal"
    monkeypatch.setenv("OLLAMA_HOST", "10.0.0.5:11434")
    assert build("ollama", SecretStore(tmp_path)).base_url == "http://10.0.0.5:11434"
