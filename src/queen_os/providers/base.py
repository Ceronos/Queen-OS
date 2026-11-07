"""Provider adapter contract.

Every adapter is a pure *codec* (``encode`` a request into URL/headers/body, ``decode``
raw response bytes into a result) plus one transport call. Queen-OS speaks each
vendor's wire protocol over raw HTTP instead of using vendor SDKs, so the exact bytes
sent and received can be hashed into an InferenceReceipt. An SDK hides those bytes.
"""

from __future__ import annotations

import re
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Literal

import httpx

from queen_os.secrets import Secret, redact
from queen_os.serial.jcs import canonicalize

ProviderKind = Literal["api", "local", "fixture"]
Role = Literal["user", "assistant"]


class ProviderError(RuntimeError):
    pass


@dataclass(frozen=True)
class Message:
    role: Role
    content: str


@dataclass(frozen=True)
class InferenceRequest:
    model: str
    messages: tuple[Message, ...]
    system: str | None = None
    max_tokens: int = 1024
    temperature: float | None = None

    def __post_init__(self) -> None:
        if not self.messages:
            raise ValueError("an inference request needs at least one message")
        if self.max_tokens <= 0:
            raise ValueError("max_tokens must be positive")


@dataclass(frozen=True)
class InferenceResult:
    text: str
    finish_reason: str | None
    model_reported: str | None
    input_tokens: int | None
    output_tokens: int | None


@dataclass(frozen=True)
class WireCall:
    """Exactly what goes on the wire. ``headers`` may hold a secret and is never persisted."""

    method: str
    url: str
    headers: dict[str, str] = field(repr=False)
    body: bytes


@dataclass(frozen=True)
class Exchange:
    call: WireCall
    status: int
    response: bytes
    latency_ms: float
    result: InferenceResult


# Model-family → training lineage. Quorum decorrelation (REMEDY §1.4) is keyed on the
# *model* lineage, not the host: OpenRouter serving Claude is still Anthropic lineage.
_LINEAGES: tuple[tuple[str, str], ...] = (
    (r"^claude", "anthropic"),
    (r"^(gpt|o\d|chatgpt|text-davinci|codex)", "openai"),
    (r"^(gemini|gemma|palm)", "google"),
    (r"^(llama|meta-llama|codellama)", "meta"),
    (r"^(qwen|qwq)", "alibaba"),
    (r"^(mistral|mixtral|codestral|devstral|magistral|ministral|pixtral)", "mistral"),
    (r"^deepseek", "deepseek"),
    (r"^grok", "xai"),
    (r"^phi", "microsoft"),
    (r"^(command|c4ai|aya)", "cohere"),
    (r"^(kimi|moonshot)", "moonshot"),
    (r"^(glm|chatglm)", "zhipu"),
    (r"^(hermes|nous)", "nous"),
    (r"^(granite)", "ibm"),
    (r"^(nemotron)", "nvidia"),
)


def lineage_of(model: str) -> str:
    name = model.lower().rsplit("/", 1)[-1]
    for pattern, lineage in _LINEAGES:
        if re.match(pattern, name):
            return lineage
    return f"unknown:{name.split(':', 1)[0]}"


class Provider(ABC):
    """One configured endpoint (e.g. ``anthropic``, ``ollama@localhost``, ``lmstudio``)."""

    name: str
    kind: ProviderKind
    base_url: str
    credential: Secret | None

    def __init__(self, name: str, kind: ProviderKind, base_url: str, credential: Secret | None) -> None:
        self.name = name
        self.kind = kind
        self.base_url = base_url.rstrip("/")
        self.credential = credential

    @abstractmethod
    def encode(self, request: InferenceRequest) -> WireCall: ...

    @abstractmethod
    def decode(self, raw: bytes) -> InferenceResult: ...

    def lineage(self, model: str) -> str:
        return lineage_of(model)

    @staticmethod
    def json_body(payload: dict[str, Any]) -> bytes:
        return canonicalize(payload)

    def _key(self) -> str:
        if self.credential is None:
            raise ProviderError(f"provider {self.name} needs a credential")
        return self.credential.reveal()

    def send(self, request: InferenceRequest, client: httpx.Client, timeout_s: float = 120.0) -> Exchange:
        call = self.encode(request)
        start = time.perf_counter()
        try:
            resp = client.request(call.method, call.url, headers=call.headers, content=call.body, timeout=timeout_s)
        except httpx.HTTPError as exc:
            raise ProviderError(redact(f"{self.name}: transport error {type(exc).__name__}: {exc}")) from None
        latency = (time.perf_counter() - start) * 1000
        raw = resp.content
        if resp.status_code >= 400:
            secrets = [self.credential] if self.credential else []
            snippet = redact(raw[:500].decode("utf-8", "replace"), secrets)
            raise ProviderError(f"{self.name}: HTTP {resp.status_code}: {snippet}")
        return Exchange(call, resp.status_code, raw, latency, self.decode(raw))
