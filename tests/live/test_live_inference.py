from __future__ import annotations

from pathlib import Path

import pytest

from queen_os.hive import Hive
from queen_os.providers import InferenceRequest, Message, build
from queen_os.providers.receipt import Inference, verify_receipt
from queen_os.secrets import SecretError, SecretStore, find_secrets

pytestmark = pytest.mark.live


def test_witnessed_inference_in_a_production_hive(target: tuple[str, str], tmp_path: Path) -> None:
    provider_name, model = target
    try:
        provider = build(provider_name, SecretStore(tmp_path / "home"))
    except SecretError as exc:
        pytest.skip(f"{provider_name}: no credential available ({exc.__class__.__name__})")
    request = InferenceRequest(
        model,
        (Message("user", "Reply with one word: the insect that builds a comb."),),
        system="You answer in one lowercase word.",
        max_tokens=32,
        temperature=0.0,
    )
    with Hive.init(tmp_path / "hive", "live", mode="production") as hive:
        witnessed = Inference(hive).run(provider, request, actor=f"live:{provider_name}")
        receipt = witnessed.receipt.payload

        assert witnessed.result.text.strip(), "real model returned no text"
        assert receipt["provider_kind"] in ("api", "local")
        assert receipt["http_status"] == 200 and receipt["latency_ms"] > 0
        assert receipt["output_tokens"] is None or receipt["output_tokens"] > 0
        assert verify_receipt(hive, witnessed.receipt).text == witnessed.result.text
        assert hive.ledger.verify_chain(require_signatures=True) == 2

        # Nothing persisted by the hive may contain credential material.
        for f in hive.root.rglob("*"):
            if f.is_file() and f.suffix not in (".pem",):
                assert not find_secrets(f.read_bytes().decode("utf-8", "replace")), f
        if provider.credential is not None:
            key = provider.credential.reveal().encode()
            assert not any(key in f.read_bytes() for f in hive.root.rglob("*") if f.is_file())
        print(
            f"\n[{provider_name}:{model}] -> {witnessed.result.text.strip()!r} "
            f"lineage={receipt['lineage']} latency={receipt['latency_ms']}ms"
        )
