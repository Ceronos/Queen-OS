from __future__ import annotations

from pathlib import Path

import pytest

from queen_os.hive import Hive
from queen_os.providers import FixtureProvider, InferenceRequest, Message
from queen_os.providers.receipt import RECEIPT_KIND, Inference, NonSimulationViolation, verify_receipt
from queen_os.secrets import Secret

REQ = InferenceRequest("fixture-model", (Message("user", "lay an egg"),))


def test_fixture_is_refused_in_production_before_it_runs(tmp_path: Path) -> None:
    """Two-arm: a fixture in a production hive must fail closed and leave no trace."""
    with Hive.init(tmp_path / "h", "prod") as hive:
        provider = FixtureProvider("scripted", ["fake work"])
        with pytest.raises(NonSimulationViolation):
            Inference(hive).run(provider, REQ, actor="worker:1")
        assert [e.kind for e in hive.ledger.events()] == ["hive.genesis"]
        assert provider._replies == ["fake work"]  # never invoked


def test_receipt_is_signed_rederivable_and_labels_fixture(tmp_path: Path) -> None:
    with Hive.init(tmp_path / "h", "lab", mode="test") as hive:
        w = Inference(hive).run(FixtureProvider("scripted", ["egg laid"]), REQ, actor="worker:1")
        assert w.result.text == "egg laid"
        p = w.receipt.payload
        assert w.receipt.kind == RECEIPT_KIND and p["provider_kind"] == "fixture" and p["credential_fp"] is None
        assert w.receipt.signer is not None
        assert verify_receipt(hive, w.receipt).text == "egg laid"
        assert hive.ledger.verify_chain(require_signatures=True) == 2


def test_receipt_with_corrupted_raw_bytes_fails(tmp_path: Path) -> None:
    with Hive.init(tmp_path / "h", "lab", mode="test") as hive:
        w = Inference(hive).run(FixtureProvider("scripted", ["x"]), REQ, actor="w")
        blob = hive.root / "comb" / "blobs" / w.receipt.payload["response_sha"][:2] / w.receipt.payload["response_sha"]
        blob.chmod(0o644)
        blob.write_bytes(b'{"text":"y","model":"fixture-model"}')
        with pytest.raises(NonSimulationViolation):
            verify_receipt(hive, w.receipt)


def test_receipt_claim_that_disagrees_with_raw_bytes_fails(tmp_path: Path) -> None:
    """A receipt appended with a fabricated completion hash can't be re-derived."""
    with Hive.init(tmp_path / "h", "lab", mode="test") as hive:
        w = Inference(hive).run(FixtureProvider("scripted", ["real text"]), REQ, actor="w")
        forged = dict(w.receipt.payload, completion_sha="0" * 64)
        ev = hive.ledger.append(RECEIPT_KIND, "w", forged)
        with pytest.raises(NonSimulationViolation, match="completion_sha"):
            verify_receipt(hive, ev)


def test_test_mode_receipt_rejected_once_hive_is_production(tmp_path: Path) -> None:
    root = tmp_path / "h"
    with Hive.init(root, "lab", mode="test") as hive:
        seq = Inference(hive).run(FixtureProvider("s", ["x"]), REQ, actor="w").receipt.seq
    manifest = (root / "hive.json").read_text().replace('"mode":"test"', '"mode":"production"')
    (root / "hive.json").chmod(0o644)
    (root / "hive.json").write_text(manifest)
    with Hive.open(root) as hive:
        ev = hive.ledger.get(seq)
        assert ev is not None
        with pytest.raises(NonSimulationViolation, match="fixture"):
            verify_receipt(hive, ev)


class LeakyFixture(FixtureProvider):
    def __init__(self) -> None:
        super().__init__("leaky", [])
        self.credential = Secret("very-secret-token-0123456789")

    def send(self, request, client, timeout_s=120.0):  # type: ignore[no-untyped-def,override]
        self._replies = [f"the key is {self.credential.reveal()}"]  # type: ignore[union-attr]
        return super().send(request, client, timeout_s)


def test_credential_echoed_in_response_is_never_persisted(tmp_path: Path) -> None:
    with Hive.init(tmp_path / "h", "lab", mode="test") as hive:
        with pytest.raises(NonSimulationViolation, match="credential"):
            Inference(hive).run(LeakyFixture(), REQ, actor="w")
        blobs = list((hive.root / "comb" / "blobs").rglob("*"))
        assert not any(b.is_file() and b"very-secret-token" in b.read_bytes() for b in blobs)
