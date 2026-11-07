"""Wire codecs for the major model APIs and local runtimes."""

from __future__ import annotations

import json
from typing import Any
from urllib.parse import quote

from queen_os.providers.base import (
    InferenceRequest,
    InferenceResult,
    Provider,
    ProviderError,
    ProviderKind,
    WireCall,
)
from queen_os.secrets import Secret


def _loads(raw: bytes, who: str) -> dict[str, Any]:
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ProviderError(f"{who}: response is not JSON ({exc.msg})") from None
    if not isinstance(data, dict):
        raise ProviderError(f"{who}: response is not a JSON object")
    return data


class AnthropicProvider(Provider):
    API_VERSION = "2023-06-01"

    def __init__(self, credential: Secret | None, base_url: str = "https://api.anthropic.com", name: str = "anthropic"):
        super().__init__(name, "api", base_url, credential)

    def encode(self, request: InferenceRequest) -> WireCall:
        payload: dict[str, Any] = {
            "model": request.model,
            "max_tokens": request.max_tokens,
            "messages": [{"role": m.role, "content": m.content} for m in request.messages],
        }
        if request.system:
            payload["system"] = request.system
        if request.temperature is not None:
            payload["temperature"] = request.temperature
        headers = {
            "x-api-key": self._key(),
            "anthropic-version": self.API_VERSION,
            "content-type": "application/json",
        }
        return WireCall("POST", f"{self.base_url}/v1/messages", headers, self.json_body(payload))

    def decode(self, raw: bytes) -> InferenceResult:
        data = _loads(raw, self.name)
        if data.get("type") == "error":
            raise ProviderError(f"{self.name}: {data.get('error', {}).get('type')}")
        text = "".join(b.get("text", "") for b in data.get("content", []) if b.get("type") == "text")
        usage = data.get("usage") or {}
        return InferenceResult(
            text, data.get("stop_reason"), data.get("model"), usage.get("input_tokens"), usage.get("output_tokens")
        )


class OpenAICompatibleProvider(Provider):
    """OpenAI Chat Completions wire format: OpenAI itself and every compatible server."""

    def __init__(
        self,
        name: str,
        base_url: str,
        credential: Secret | None,
        kind: ProviderKind = "api",
        max_tokens_field: str = "max_tokens",
        extra_headers: dict[str, str] | None = None,
    ):
        super().__init__(name, kind, base_url, credential)
        self.max_tokens_field = max_tokens_field
        self.extra_headers = extra_headers or {}

    def encode(self, request: InferenceRequest) -> WireCall:
        messages = [{"role": "system", "content": request.system}] if request.system else []
        messages += [{"role": m.role, "content": m.content} for m in request.messages]
        payload: dict[str, Any] = {
            "model": request.model,
            "messages": messages,
            self.max_tokens_field: request.max_tokens,
            "stream": False,
        }
        if request.temperature is not None:
            payload["temperature"] = request.temperature
        headers = {"content-type": "application/json", **self.extra_headers}
        if self.credential is not None:
            headers["authorization"] = f"Bearer {self._key()}"
        return WireCall("POST", f"{self.base_url}/chat/completions", headers, self.json_body(payload))

    def decode(self, raw: bytes) -> InferenceResult:
        data = _loads(raw, self.name)
        if "error" in data:
            err = data["error"]
            raise ProviderError(f"{self.name}: {err.get('type') or err.get('code') if isinstance(err, dict) else err}")
        choices = data.get("choices") or []
        if not choices:
            raise ProviderError(f"{self.name}: response has no choices")
        message = choices[0].get("message") or {}
        content = message.get("content")
        if isinstance(content, list):  # some servers return content parts
            content = "".join(p.get("text", "") for p in content if isinstance(p, dict))
        usage = data.get("usage") or {}
        return InferenceResult(
            content or "",
            choices[0].get("finish_reason"),
            data.get("model"),
            usage.get("prompt_tokens"),
            usage.get("completion_tokens"),
        )


class GeminiProvider(Provider):
    def __init__(
        self,
        credential: Secret | None,
        base_url: str = "https://generativelanguage.googleapis.com",
        name: str = "gemini",
    ):
        super().__init__(name, "api", base_url, credential)

    def encode(self, request: InferenceRequest) -> WireCall:
        contents = [
            {"role": "model" if m.role == "assistant" else "user", "parts": [{"text": m.content}]}
            for m in request.messages
        ]
        config: dict[str, Any] = {"maxOutputTokens": request.max_tokens}
        if request.temperature is not None:
            config["temperature"] = request.temperature
        payload: dict[str, Any] = {"contents": contents, "generationConfig": config}
        if request.system:
            payload["systemInstruction"] = {"parts": [{"text": request.system}]}
        # Key goes in a header, never the query string, so URLs are safe to log.
        headers = {"x-goog-api-key": self._key(), "content-type": "application/json"}
        url = f"{self.base_url}/v1beta/models/{quote(request.model, safe='')}:generateContent"
        return WireCall("POST", url, headers, self.json_body(payload))

    def decode(self, raw: bytes) -> InferenceResult:
        data = _loads(raw, self.name)
        if "error" in data:
            raise ProviderError(f"{self.name}: {data['error'].get('status')}")
        candidates = data.get("candidates") or []
        if not candidates:
            block = (data.get("promptFeedback") or {}).get("blockReason")
            raise ProviderError(f"{self.name}: no candidates (blockReason={block})")
        parts = (candidates[0].get("content") or {}).get("parts") or []
        text = "".join(p.get("text", "") for p in parts if not p.get("thought"))
        usage = data.get("usageMetadata") or {}
        return InferenceResult(
            text,
            candidates[0].get("finishReason"),
            data.get("modelVersion"),
            usage.get("promptTokenCount"),
            usage.get("candidatesTokenCount"),
        )


class OllamaProvider(Provider):
    """Ollama native ``/api/chat`` (Ollama also serves an OpenAI-compatible ``/v1``)."""

    def __init__(
        self, base_url: str = "http://localhost:11434", credential: Secret | None = None, name: str = "ollama"
    ):
        super().__init__(name, "local", base_url, credential)

    def encode(self, request: InferenceRequest) -> WireCall:
        messages = [{"role": "system", "content": request.system}] if request.system else []
        messages += [{"role": m.role, "content": m.content} for m in request.messages]
        options: dict[str, Any] = {"num_predict": request.max_tokens}
        if request.temperature is not None:
            options["temperature"] = request.temperature
        payload = {"model": request.model, "messages": messages, "stream": False, "options": options}
        headers = {"content-type": "application/json"}
        if self.credential is not None:  # Ollama behind an authenticating proxy / ollama.com
            headers["authorization"] = f"Bearer {self._key()}"
        return WireCall("POST", f"{self.base_url}/api/chat", headers, self.json_body(payload))

    def decode(self, raw: bytes) -> InferenceResult:
        data = _loads(raw, self.name)
        if "error" in data:
            raise ProviderError(f"{self.name}: {data['error']}")
        message = data.get("message") or {}
        return InferenceResult(
            message.get("content", ""),
            data.get("done_reason"),
            data.get("model"),
            data.get("prompt_eval_count"),
            data.get("eval_count"),
        )
