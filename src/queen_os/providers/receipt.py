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

import math
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
from queen_os.providers.structured import (
    JsonSchemaOutput,
    StructuredOutputError,
    has_output_mode,
    request_schema,
    response_fields,
    strict_json,
)
from queen_os.serial.afser import DigestDivergence, sha256_hex

RECEIPT_KIND = "inference.receipt"


class NonSimulationViolation(PermissionError):
    """A fixture tried to run in a production hive, or a receipt doesn't match its bytes."""


class StructuredOutputRejected(NonSimulationViolation):
    """A received response failed the output contract; its signed receipt is retained."""

    def __init__(self, receipt: Event):
        self.receipt = receipt
        super().__init__(f"structured output rejected; evidence retained at receipt seq {receipt.seq}")


def _structured_result(
    codec: str, request_raw: bytes, response_raw: bytes, output: JsonSchemaOutput, status: int
) -> tuple[InferenceResult | None, str | None]:
    try:
        if type(status) is not int or not 200 <= status < 300:
            raise StructuredOutputError("unsuccessful_http_status")
        if request_schema(codec, request_raw).schema_bytes != output.schema_bytes:
            raise StructuredOutputError("wire_schema_mismatch")
        result = InferenceResult(**response_fields(codec, response_raw))
        output.validate(result.text)
        return result, None
    except StructuredOutputError:
        return None, "structured_contract_rejected"


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

    def run(
        self,
        provider: Provider,
        request: InferenceRequest,
        actor: str,
        capability: Capability,
        *,
        timeout_s: float | None = None,
    ) -> Witnessed:
        """One witnessed call. ``capability`` must grant this actor/provider/model/size.

        Order: refuse fixtures in production, then authorize and reserve budget (ledger),
        then call, then persist and sign. A call that fails after authorization still consumes
        its budget, which errs on the side of fail-closed.
        """
        if provider.kind == "fixture" and self.hive.mode != "test":
            raise NonSimulationViolation(
                f"fixture provider {provider.name!r} refused: hive {self.hive.node_id} is a production hive"
            )
        if timeout_s is not None and (not math.isfinite(timeout_s) or timeout_s <= 0):
            raise ValueError("timeout must be finite and positive")
        from queen_os.workers.execution import validate_inference

        validate_inference(self.hive, provider, request, actor, capability)
        provider.validate_request(request)
        codec = codec_of(provider)
        spend_seq = self.hive.authority().authorize_inference(
            capability, actor, provider.name, request.model, request.max_tokens
        )
        exchange = (
            provider.send(request, self.client)
            if timeout_s is None
            else provider.send(request, self.client, timeout_s=timeout_s)
        )
        if provider.credential is not None:
            key = provider.credential.reveal().encode()
            if key in exchange.call.body or key in exchange.response:
                raise NonSimulationViolation("credential material found in wire body; refusing to persist it")
        request_sha = self.hive.blobs.put(exchange.call.body)
        response_sha = self.hive.blobs.put(exchange.response)
        result = exchange.result
        structured: dict[str, Any] | None = None
        if request.output is not None:
            schema_sha = self.hive.blobs.put(request.output.schema_bytes)
            result, failure = _structured_result(
                codec, exchange.call.body, exchange.response, request.output, exchange.status
            )
            structured = {
                "v": 1,
                "schema_sha": schema_sha,
                "decoder_v": 1,
                "valid": result is not None,
                "failure": failure,
            }
        elif result is None:
            raise NonSimulationViolation("text provider returned no decoded result")
        model = (result.model_reported if result is not None else None) or request.model
        payload: dict[str, Any] = {
            "v": 2 if structured is not None else 1,
            "provider": provider.name,
            "provider_kind": provider.kind,
            "codec": codec,
            "lineage": provider.lineage(model),
            "endpoint": _endpoint(exchange.call.url),
            "model_requested": request.model,
            "model_reported": result.model_reported if result is not None else None,
            "request_sha": request_sha,
            "response_sha": response_sha,
            "completion_sha": sha256_hex(result.text.encode("utf-8")) if result is not None else None,
            "http_status": exchange.status,
            "latency_ms": round(exchange.latency_ms, 3),
            "input_tokens": result.input_tokens if result is not None else None,
            "output_tokens": result.output_tokens if result is not None else None,
            "finish_reason": result.finish_reason if result is not None else None,
            "credential_fp": provider.credential.fingerprint if provider.credential else None,
            "token_id": capability.token_id,
            "spend_seq": spend_seq,
            "host": {"os": sys.platform, "machine": platform.machine(), "python": platform.python_version()},
        }
        if structured is not None:
            payload["structured_output"] = structured
        event = self.hive.ledger.append(RECEIPT_KIND, actor, payload)
        if result is None:
            raise StructuredOutputRejected(event)
        return Witnessed(result, event)


def verify_receipt(hive: Hive, event: Event) -> InferenceResult:
    """Re-derive a receipt from its stored bytes. Raises NonSimulationViolation on any mismatch."""
    if event.kind != RECEIPT_KIND:
        raise NonSimulationViolation(f"seq {event.seq} is not an inference receipt")
    p = event.payload
    if type(p.get("v")) is not int or p["v"] not in (1, 2):
        raise NonSimulationViolation("unsupported receipt version")
    if p["provider_kind"] == "fixture" and hive.mode != "test":
        raise NonSimulationViolation(f"seq {event.seq}: fixture receipt in a production hive")
    try:
        raw = hive.blobs.get(p["response_sha"])
        request_raw = hive.blobs.get(p["request_sha"])
    except (OSError, DigestDivergence) as exc:
        raise NonSimulationViolation(f"seq {event.seq}: raw bytes missing ({exc})") from None
    spend = hive.ledger.get(p["spend_seq"])
    if spend is None or spend.kind != SPENT or spend.payload["token_id"] != p["token_id"] or spend.seq >= event.seq:
        raise NonSimulationViolation(f"seq {event.seq}: no prior capability spend authorizes this call")
    if hive.ledger.find_op(f"{ISSUED}:{p['token_id']}") is None:
        raise NonSimulationViolation(f"seq {event.seq}: authorizing token was never issued by this hive")
    if spend.payload["action"] != {"type": "inference", "provider": p["provider"], "model": p["model_requested"]}:
        raise NonSimulationViolation(f"seq {event.seq}: spend authorized a different provider/model")
    if p["v"] == 2:
        try:
            contract = p["structured_output"]
            if (
                set(contract) != {"v", "schema_sha", "decoder_v", "valid", "failure"}
                or type(contract["v"]) is not int
                or contract["v"] != 1
                or type(contract["decoder_v"]) is not int
                or contract["decoder_v"] != 1
            ):
                raise StructuredOutputError("unsupported_contract_version")
            schema_raw = hive.blobs.get(contract["schema_sha"])
            output = JsonSchemaOutput(strict_json(schema_raw))
            if output.schema_bytes != schema_raw:
                raise StructuredOutputError("noncanonical_schema")
            result, failure = _structured_result(p["codec"], request_raw, raw, output, p["http_status"])
            if (
                type(contract["valid"]) is not bool
                or contract["valid"] != (result is not None)
                or contract["failure"] != failure
            ):
                raise StructuredOutputError("contract_claim_mismatch")
        except (KeyError, TypeError, ValueError, OSError, DigestDivergence) as exc:
            raise NonSimulationViolation(f"seq {event.seq}: invalid structured evidence") from exc
        if result is None:
            raise NonSimulationViolation(f"seq {event.seq}: structured output was rejected")
    else:
        try:
            request_body = strict_json(request_raw)
            if not isinstance(request_body, dict):
                raise NonSimulationViolation("invalid request evidence")
            if "structured_output" in p or has_output_mode(p["codec"], request_body):
                raise NonSimulationViolation("structured request cannot use a v1 receipt")
        except (ValueError, TypeError) as exc:
            raise NonSimulationViolation("invalid request evidence") from exc
        result = decoder_for(p["codec"])(raw)
    checks = {
        "completion_sha": sha256_hex(result.text.encode("utf-8")),
        "model_reported": result.model_reported,
        "input_tokens": result.input_tokens,
        "output_tokens": result.output_tokens,
        "finish_reason": result.finish_reason,
    }
    for key, derived in checks.items():
        if p[key] != derived or (p["v"] == 2 and type(p[key]) is not type(derived)):
            raise NonSimulationViolation(f"seq {event.seq}: receipt field {key} does not match raw response")
    return result
