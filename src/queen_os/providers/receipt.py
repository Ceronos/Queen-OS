"""InferenceReceipts (AF-REMEDY-V1 §1.1): every model call is witnessed.

R = ⟨model id, h_prompt, h_completion, Δt, hardware envelope, raw bytes, σ_collector⟩

* The exact request body and response bytes are stored in the hive's content-addressed
  blob store, and the receipt references them by SHA-256.
* The receipt is a ledger event, so the host key signs it (σ_collector) and the hash chain orders it.
* :func:`verify_receipt` re-decodes the stored raw response with the provider's codec
  and checks every claim in the receipt against it. A receipt that can't be re-derived
  from its own bytes fails.
* A fixture provider records ``provider_kind: "fixture"`` inside the signed receipt and
  is refused in production hives *before* it runs.
"""

from __future__ import annotations

import platform
import sys
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit

import httpx

from queen_os.authority.tokens import ISSUED, SPENT, Capability
from queen_os.comb.ledger import Event
from queen_os.hive import Hive
from queen_os.providers.base import InferenceRequest, InferenceResult, Provider
from queen_os.providers.registry import codec_of, decoder_for
from queen_os.serial.afser import DigestDivergence, sha256_hex

RECEIPT_KIND = "inference.receipt"


class NonSimulationViolation(PermissionError):
    """A fixture tried to run in a production hive, or a receipt doesn't match its bytes."""


@dataclass(frozen=True)
class Witnessed:
    result: InferenceResult
    receipt: Event


def _endpoint(url: str) -> str:
    parts = urlsplit(url)
    return f"{parts.scheme}://{parts.netloc}{parts.path}"  # never the query string


class Inference:
    def __init__(self, hive: Hive, client: httpx.Client | None = None) -> None:
        self.hive = hive
        self.client = client or httpx.Client(follow_redirects=False)

    def run(self, provider: Provider, request: InferenceRequest, actor: str, capability: Capability) -> Witnessed:
        """One witnessed call. ``capability`` must grant this actor/provider/model/size.

        Order: refuse fixtures in production, then authorize and reserve budget (ledger),
        then call, then persist and sign. A call that fails after authorization still consumes
        its budget, which errs on the side of fail-closed.
        """
        if provider.kind == "fixture" and self.hive.mode != "test":
            raise NonSimulationViolation(
                f"fixture provider {provider.name!r} refused: hive {self.hive.node_id} is a production hive"
            )
        spend_seq = self.hive.authority().authorize_inference(
            capability, actor, provider.name, request.model, request.max_tokens
        )
        exchange = provider.send(request, self.client)
        if provider.credential is not None:
            key = provider.credential.reveal().encode()
            if key in exchange.call.body or key in exchange.response:
                raise NonSimulationViolation("credential material found in wire body; refusing to persist it")
        request_sha = self.hive.blobs.put(exchange.call.body)
        response_sha = self.hive.blobs.put(exchange.response)
        result = exchange.result
        model = result.model_reported or request.model
        payload: dict[str, Any] = {
            "v": 1,
            "provider": provider.name,
            "provider_kind": provider.kind,
            "codec": codec_of(provider),
            "lineage": provider.lineage(model),
            "endpoint": _endpoint(exchange.call.url),
            "model_requested": request.model,
            "model_reported": result.model_reported,
            "request_sha": request_sha,
            "response_sha": response_sha,
            "completion_sha": sha256_hex(result.text.encode("utf-8")),
            "http_status": exchange.status,
            "latency_ms": round(exchange.latency_ms, 3),
            "input_tokens": result.input_tokens,
            "output_tokens": result.output_tokens,
            "finish_reason": result.finish_reason,
            "credential_fp": provider.credential.fingerprint if provider.credential else None,
            "token_id": capability.token_id,
            "spend_seq": spend_seq,
            "host": {"os": sys.platform, "machine": platform.machine(), "python": platform.python_version()},
        }
        event = self.hive.ledger.append(RECEIPT_KIND, actor, payload)
        return Witnessed(result, event)


def verify_receipt(hive: Hive, event: Event) -> InferenceResult:
    """Re-derive a receipt from its stored bytes. Raises NonSimulationViolation on any mismatch."""
    if event.kind != RECEIPT_KIND:
        raise NonSimulationViolation(f"seq {event.seq} is not an inference receipt")
    p = event.payload
    if p["provider_kind"] == "fixture" and hive.mode != "test":
        raise NonSimulationViolation(f"seq {event.seq}: fixture receipt in a production hive")
    try:
        raw = hive.blobs.get(p["response_sha"])
        hive.blobs.get(p["request_sha"])
    except (OSError, DigestDivergence) as exc:
        raise NonSimulationViolation(f"seq {event.seq}: raw bytes missing ({exc})") from None
    spend = hive.ledger.get(p["spend_seq"])
    if spend is None or spend.kind != SPENT or spend.payload["token_id"] != p["token_id"] or spend.seq >= event.seq:
        raise NonSimulationViolation(f"seq {event.seq}: no prior capability spend authorizes this call")
    if hive.ledger.find_op(f"{ISSUED}:{p['token_id']}") is None:
        raise NonSimulationViolation(f"seq {event.seq}: authorizing token was never issued by this hive")
    if spend.payload["action"] != {"type": "inference", "provider": p["provider"], "model": p["model_requested"]}:
        raise NonSimulationViolation(f"seq {event.seq}: spend authorized a different provider/model")
    result = decoder_for(p["codec"])(raw)
    checks = {
        "completion_sha": sha256_hex(result.text.encode("utf-8")),
        "model_reported": result.model_reported,
        "input_tokens": result.input_tokens,
        "output_tokens": result.output_tokens,
        "finish_reason": result.finish_reason,
    }
    for key, derived in checks.items():
        if p[key] != derived:
            raise NonSimulationViolation(f"seq {event.seq}: receipt field {key} does not match raw response")
    return result
