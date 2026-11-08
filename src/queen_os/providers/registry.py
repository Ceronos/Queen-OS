"""Built-in provider presets. Each one resolves its credential through the SecretStore.

Base-URL overrides use ``QUEEN_<NAME>_BASE_URL`` rather than vendor variables such as
``ANTHROPIC_BASE_URL``. Other tools (IDE agents, proxies) set the vendor variables, and
silently inheriting one of them would route a hive's inference somewhere unintended.
``OLLAMA_HOST`` is the exception because it is Ollama's own documented setting.
"""

from __future__ import annotations

import json
import os
from collections.abc import Callable
from dataclasses import dataclass

import httpx

from queen_os.providers.adapters import AnthropicProvider, GeminiProvider, OllamaProvider, OpenAICompatibleProvider
from queen_os.providers.base import (
    Exchange,
    InferenceRequest,
    InferenceResult,
    Provider,
    ProviderKind,
    WireCall,
)
from queen_os.secrets import Secret, SecretStore


@dataclass(frozen=True)
class Preset:
    name: str
    codec: str
    base_url: str
    key_env: tuple[str, ...]
    kind: ProviderKind = "api"
    key_required: bool = True
    max_tokens_field: str = "max_tokens"
    extra_base_env: str | None = None
    json_schema_output: bool = False


PRESETS: dict[str, Preset] = {
    p.name: p
    for p in (
        Preset("anthropic", "anthropic", "https://api.anthropic.com", ("ANTHROPIC_API_KEY",)),
        Preset(
            "openai",
            "openai",
            "https://api.openai.com/v1",
            ("OPENAI_API_KEY",),
            max_tokens_field="max_completion_tokens",
            json_schema_output=True,
        ),
        Preset("gemini", "gemini", "https://generativelanguage.googleapis.com", ("GEMINI_API_KEY", "GOOGLE_API_KEY")),
        Preset("openrouter", "openai", "https://openrouter.ai/api/v1", ("OPENROUTER_API_KEY",)),
        Preset("groq", "openai", "https://api.groq.com/openai/v1", ("GROQ_API_KEY",)),
        Preset("deepseek", "openai", "https://api.deepseek.com/v1", ("DEEPSEEK_API_KEY",)),
        Preset("xai", "openai", "https://api.x.ai/v1", ("XAI_API_KEY",)),
        Preset("mistral", "openai", "https://api.mistral.ai/v1", ("MISTRAL_API_KEY",)),
        Preset("together", "openai", "https://api.together.xyz/v1", ("TOGETHER_API_KEY",)),
        Preset("fireworks", "openai", "https://api.fireworks.ai/inference/v1", ("FIREWORKS_API_KEY",)),
        Preset("cerebras", "openai", "https://api.cerebras.ai/v1", ("CEREBRAS_API_KEY",)),
        Preset("nous", "openai", "https://inference-api.nousresearch.com/v1", ("NOUS_API_KEY",)),
        Preset(
            "ollama",
            "ollama",
            "http://localhost:11434",
            ("OLLAMA_API_KEY",),
            kind="local",
            key_required=False,
            extra_base_env="OLLAMA_HOST",
        ),
        Preset(
            "lmstudio",
            "openai",
            "http://localhost:1234/v1",
            ("LMSTUDIO_API_KEY",),
            kind="local",
            key_required=False,
            json_schema_output=True,
        ),
        Preset("vllm", "openai", "http://localhost:8000/v1", ("VLLM_API_KEY",), kind="local", key_required=False),
        Preset(
            "llamacpp", "openai", "http://localhost:8080/v1", ("LLAMACPP_API_KEY",), kind="local", key_required=False
        ),
    )
}


def base_url_for(preset: Preset) -> str:
    override = os.environ.get(f"QUEEN_{preset.name.upper()}_BASE_URL")
    if override:
        return override
    if preset.extra_base_env and os.environ.get(preset.extra_base_env):
        host = os.environ[preset.extra_base_env]
        return host if "://" in host else f"http://{host}"
    return preset.base_url


def resolve_credential(preset: Preset, store: SecretStore) -> Secret | None:
    for env in preset.key_env:
        secret = store.get(env)
        if secret is not None:
            return secret
    return None


def build(name: str, store: SecretStore, base_url: str | None = None) -> Provider:
    if name not in PRESETS:
        raise KeyError(f"unknown provider {name!r}; known: {', '.join(sorted(PRESETS))}")
    preset = PRESETS[name]
    credential = resolve_credential(preset, store)
    if credential is None and preset.key_required:
        store.require(preset.key_env[0])  # raises with setup instructions
    url = base_url or base_url_for(preset)
    if preset.codec == "anthropic":
        return AnthropicProvider(credential, url, name)
    if preset.codec == "gemini":
        return GeminiProvider(credential, url, name)
    if preset.codec == "ollama":
        return OllamaProvider(url, credential, name)
    return OpenAICompatibleProvider(
        name,
        url,
        credential,
        preset.kind,
        preset.max_tokens_field,
        supports_structured_output=preset.json_schema_output,
    )


# Decoders by codec name, so a stored receipt can be re-derived from its raw bytes.
def _decoder(codec: str) -> Callable[[bytes], InferenceResult]:
    probe: Provider
    if codec == "anthropic":
        probe = AnthropicProvider(None)
    elif codec == "gemini":
        probe = GeminiProvider(None)
    elif codec == "ollama":
        probe = OllamaProvider()
    elif codec == "openai":
        probe = OpenAICompatibleProvider("decoder", "http://decoder", None)
    elif codec == "fixture":
        probe = FixtureProvider("decoder", [])
    else:
        raise KeyError(f"unknown codec {codec!r}")
    return probe.decode


def decoder_for(codec: str) -> Callable[[bytes], InferenceResult]:
    return _decoder(codec)


def codec_of(provider: Provider) -> str:
    if isinstance(provider, AnthropicProvider):
        return "anthropic"
    if isinstance(provider, GeminiProvider):
        return "gemini"
    if isinstance(provider, OllamaProvider):
        return "ollama"
    if isinstance(provider, OpenAICompatibleProvider):
        return "openai"
    if isinstance(provider, FixtureProvider):
        return "fixture"
    raise KeyError(type(provider).__name__)


class FixtureProvider(Provider):
    """Scripted responses for tests. Its kind is ``fixture`` and it is recorded as such
    *inside* every signed receipt. Production hives refuse to run it.
    """

    supports_structured_output = True

    def __init__(self, name: str, replies: list[str]) -> None:
        super().__init__(name, "fixture", "fixture://local", None)
        self._replies = list(replies)

    def encode(self, request: InferenceRequest) -> WireCall:
        self.validate_request(request)
        payload: dict[str, object] = {"model": request.model, "messages": [m.content for m in request.messages]}
        if request.output is not None:
            payload["output_schema"] = request.output.schema
        body = self.json_body(payload)
        return WireCall("POST", f"{self.base_url}/{self.name}", {}, body)

    def decode(self, raw: bytes) -> InferenceResult:
        data = json.loads(raw)
        return InferenceResult(str(data["text"]), "fixture", str(data["model"]), None, None)

    def send(self, request: InferenceRequest, client: httpx.Client | None, timeout_s: float = 120.0) -> Exchange:
        if not self._replies:
            raise RuntimeError("fixture provider has no scripted replies left")
        raw = self.json_body({"text": self._replies.pop(0), "model": request.model})
        call = self.encode(request)
        return Exchange(call, 200, raw, 0.0, None if request.output is not None else self.decode(raw))
