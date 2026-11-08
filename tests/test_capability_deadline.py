"""Absolute host capability deadlines; fixture clocks make drift deterministic."""

from pathlib import Path

import pytest

from queen_os.authority import AuthorityError, Grant
from queen_os.hive import Hive


@pytest.fixture
def hive(tmp_path: Path):  # type: ignore[no-untyped-def]
    with Hive.init(tmp_path / "h", "deadline", mode="test") as h:
        yield h


def test_deadline_narrows_signed_capability_and_denies_at_exact_boundary(
    hive: Hive, monkeypatch: pytest.MonkeyPatch
) -> None:
    now = [hive.ledger.now()]
    monkeypatch.setattr(hive.ledger, "now", lambda: now[0])
    auth = hive.authority()
    deadline = now[0] + 10
    grant = Grant(providers=("scripted",), models=("fixture",), max_calls=2)
    cap = auth.issue("worker:a", "egg:fixture", grant, 1000, not_after_ms=deadline)
    assert cap.expires_ms == deadline
    assert hive.ledger.find_op(f"capability.issued:{cap.token_id}").payload == cap.to_json()  # type: ignore[union-attr]
    now[0] = deadline - 1
    auth.authorize_inference(cap, "worker:a", "scripted", "fixture", 1)
    now[0] = deadline
    with pytest.raises(AuthorityError, match="validity"):
        auth.authorize_inference(cap, "worker:a", "scripted", "fixture", 1)
    assert auth.uses(cap.token_id) == 1
    assert hive.ledger.verify_chain(require_signatures=True) == 3


def test_later_deadline_never_extends_requested_ttl(hive: Hive, monkeypatch: pytest.MonkeyPatch) -> None:
    now = hive.ledger.now()
    monkeypatch.setattr(hive.ledger, "now", lambda: now)
    cap = hive.authority().issue("worker:a", "egg:fixture", Grant(), 10, not_after_ms=now + 1000)
    assert cap.not_before_ms == now and cap.expires_ms == now + 10


@pytest.mark.parametrize("delta", [0, -1])
def test_elapsed_deadline_issues_nothing(hive: Hive, monkeypatch: pytest.MonkeyPatch, delta: int) -> None:
    now, before = hive.ledger.now(), hive.ledger.head()
    monkeypatch.setattr(hive.ledger, "now", lambda: now)
    with pytest.raises(AuthorityError, match="deadline"):
        hive.authority().issue("worker:a", "egg:fixture", Grant(), 10, not_after_ms=now + delta)
    assert hive.ledger.head() == before


@pytest.mark.parametrize("deadline", [True, 1.5, "10000"])
def test_ambiguous_deadline_type_issues_nothing(hive: Hive, deadline: object) -> None:
    before = hive.ledger.head()
    with pytest.raises(ValueError, match="integer"):
        hive.authority().issue("worker:a", "egg:fixture", Grant(), 10, not_after_ms=deadline)  # type: ignore[arg-type]
    assert hive.ledger.head() == before
