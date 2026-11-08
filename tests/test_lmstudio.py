"""Offline native lifecycle and schema-wire tests; injected effects are fixture-marked."""

from __future__ import annotations

import copy
import json
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier, Lock

import httpx
import pytest

from queen_os.authority import Grant
from queen_os.cli import main
from queen_os.hive import Hive
from queen_os.providers import InferenceRequest, JsonSchemaOutput, Message
from queen_os.providers.lmstudio import LMStudio, LocalModelError, local_root
from queen_os.providers.receipt import Inference, verify_receipt
from queen_os.providers.registry import build
from queen_os.secrets import SecretStore

MODEL = "fixture/example-llm-q4"


def inventory(instances=None):
    return {
        "models": [
            {
                "type": "llm",
                "key": MODEL,
                "size_bytes": 1024,
                "max_context_length": 4096,
                "loaded_instances": instances or [],
            }
        ]
    }


def loaded(instance_id="fixture-instance", context=2048):
    return {"id": instance_id, "config": {"context_length": context}}


@pytest.fixture
def hive(tmp_path):
    with Hive.init(tmp_path / "hive", "lmstudio_test", mode="test") as value:
        yield value


def server(*, fault=None):
    state = inventory()
    calls = []

    def handle(request):
        calls.append((request.method, request.url.path))
        assert request.url.host == "127.0.0.1" and "authorization" not in request.headers
        if request.method == "GET":
            return httpx.Response(200, json=state)
        body = json.loads(request.content)
        if request.url.path.endswith("/load"):
            assert body == {"model": MODEL, "context_length": 2048, "echo_load_config": True}
            state["models"][0]["loaded_instances"] = [loaded()]
            if fault == "timeout_after_effect":
                raise httpx.ReadTimeout("synthetic private detail")
            response = {
                "type": "llm",
                "instance_id": "fixture-instance",
                "status": "loaded",
                "load_config": {"context_length": 2048},
            }
            if fault == "wrong_context":
                response["load_config"]["context_length"] = 8192
            if fault == "wrong_instance":
                response["instance_id"] = "different-instance"
            return httpx.Response(200, json=response)
        assert request.url.path == "/api/v1/models/unload"
        assert body == {"instance_id": "fixture-instance"}
        state["models"][0]["loaded_instances"] = []
        return httpx.Response(200, json={"instance_id": "fixture-instance"})

    return LMStudio(transport=httpx.MockTransport(handle)), state, calls


@pytest.mark.parametrize(
    "url",
    [
        "https://127.0.0.1:1234",
        "http://example.com:1234",
        "http://192.168.1.2:1234",
        "http://127.0.0.1:0",
        "http://127.0.0.1:65536",
        "http://user:password@127.0.0.1",
        "http://127.0.0.1?key=private",
        "http://127.0.0.1#secret",
        "http://127.0.0.1/api/v1",
        "http://127.0.0.1\n:1234",
    ],
)
def test_remote_credential_and_ambiguous_endpoints_refused(url):
    with pytest.raises(LocalModelError):
        local_root(url)


def test_local_endpoints_are_canonical_without_dns():
    assert local_root("http://localhost:1234/v1/") == "http://127.0.0.1:1234"
    assert local_root("http://[::1]:4567/v1") == "http://[::1]:4567"


def test_one_load_then_specific_unload_are_signed_and_read_back(hive):
    manager, _, calls = server()
    result = manager.change(hive, "load-1", "load", MODEL)
    assert result["desired_state_observed"] is True and result["instance_id"] == "fixture-instance"
    assert result["fixture"] is True and result["causality"] == "not_established_by_readback"
    intent = hive.ledger.find_op("local-model:load-1:intent")
    assert intent.kind == "local_model.intent" and intent.payload["fixture"] is True
    result = manager.change(hive, "unload-1", "unload", "fixture-instance")
    assert result["desired_state_observed"] is True
    assert [path for method, path in calls if method == "POST"] == ["/api/v1/models/load", "/api/v1/models/unload"]
    assert hive.ledger.verify_chain(require_signatures=True) == 7
    assert all(e.payload.get("fixture") is True for e in hive.ledger.events(after=1))


@pytest.mark.parametrize("fault", [None, "timeout_after_effect", "wrong_context", "wrong_instance"])
def test_repeated_operation_never_repeats_post_and_status_only_reads(hive, fault):
    manager, _, calls = server(fault=fault)
    if fault:
        with pytest.raises(LocalModelError, match="effect_unknown_use_status_no_retry"):
            manager.change(hive, "stable", "load", MODEL)
    else:
        manager.change(hive, "stable", "load", MODEL)
    before = len(calls)
    with pytest.raises(LocalModelError, match="operation_already_recorded"):
        manager.change(hive, "stable", "load", MODEL)
    assert len(calls) == before
    result = manager.status(hive, "stable")
    assert calls[-1] == ("GET", "/api/v1/models")
    assert result["desired_state_observed"] is (fault != "wrong_instance")
    assert len([c for c in calls if c[0] == "POST"]) == 1
    assert "synthetic private detail" not in json.dumps([e.payload for e in hive.ledger.events()])
    if fault:
        assert list(hive.ledger.events(kind="local_model.unknown"))


@pytest.mark.parametrize(
    "kwargs",
    [
        {"target": "not-installed"},
        {"target": MODEL, "context_length": 4097},
        {"target": MODEL, "context_length": True},
        {"target": MODEL, "max_weights_bytes": 100},
        {"target": MODEL, "max_weights_bytes": False},
        {"target": MODEL, "action": "download"},
        {"target": MODEL, "operation_id": "invalid / id"},
    ],
)
def test_invalid_missing_or_over_budget_request_has_no_effect_or_intent(hive, kwargs):
    manager, _, calls = server()
    args = {"operation_id": "test", "action": "load", **kwargs}
    with pytest.raises(LocalModelError):
        manager.change(hive, **args)
    assert not any(c[0] == "POST" for c in calls)
    assert [e.kind for e in hive.ledger.events()] == ["hive.genesis"]


def test_already_loaded_model_is_not_loaded_again_and_unload_requires_exact_instance(hive):
    manager, state, calls = server()
    state["models"][0]["loaded_instances"] = [loaded("someone-elses-instance")]
    for action, target in [("load", MODEL), ("unload", MODEL), ("unload", "unknown")]:
        with pytest.raises(LocalModelError):
            manager.change(hive, "no-effect", action, target)
    assert not any(method == "POST" for method, _ in calls)


@pytest.mark.parametrize(
    "data",
    [
        {"models": []},
        {"models": [None]},
        {"models": [{"type": []}]},
        {"models": [inventory()["models"][0]] * 2},
        {"models": [{**inventory()["models"][0], "size_bytes": True}]},
        {"models": [{**inventory()["models"][0], "loaded_instances": [loaded(), loaded()]}]},
    ],
)
def test_empty_or_malformed_inventory_never_permits_load(hive, data):
    calls = []

    def respond(request):
        calls.append(request.method)
        return httpx.Response(200, json=data)

    manager = LMStudio(transport=httpx.MockTransport(respond))
    with pytest.raises(LocalModelError):
        manager.change(hive, "refuse", "load", MODEL)
    assert calls == ["GET"]


@pytest.mark.parametrize("kind", ["redirect", "oversize", "duplicate", "nonfinite", "http_error"])
def test_untrusted_http_reply_is_bounded_and_not_followed(kind):
    calls = []

    def respond(request):
        calls.append(request.url.path)
        if kind == "redirect":
            return httpx.Response(302, headers={"location": "https://outside.example/"})
        if kind == "oversize":
            return httpx.Response(200, content=b" " * (1024 * 1024 + 1))
        if kind == "duplicate":
            return httpx.Response(200, content=b'{"models":[],"models":[]}')
        if kind == "nonfinite":
            return httpx.Response(200, content=b'{"models":NaN}')
        return httpx.Response(401, content=b"do not export private body")

    with pytest.raises(LocalModelError):
        LMStudio(transport=httpx.MockTransport(respond)).models()
    assert calls == ["/api/v1/models"]


def test_production_hive_refuses_fixture_transport(tmp_path):
    manager, _, calls = server()
    with (
        Hive.init(tmp_path / "production", "test") as production,
        pytest.raises(LocalModelError, match="fixture_lifecycle_refused"),
    ):
        manager.change(production, "test", "load", MODEL)
    assert calls == []


@pytest.mark.parametrize("target", ["", "x" * 513, "bad\nname", "e\u0301", "\ud800"])
def test_invalid_identifiers_refuse_before_network(hive, target):
    manager, _, calls = server()
    with pytest.raises(LocalModelError, match="invalid_model_identifier"):
        manager.change(hive, "identifier", "load", target)
    assert calls == []


def test_intent_readback_failure_does_not_send_and_cannot_be_replayed(hive, monkeypatch):
    manager, _, calls = server()
    original = hive.ledger._post_write_fetch

    def fail(_):
        raise OSError("synthetic committed-intent readback failure")

    monkeypatch.setattr(hive.ledger, "_post_write_fetch", fail)
    with pytest.raises(OSError):
        manager.change(hive, "unknown", "load", MODEL)
    assert hive.ledger.find_op("local-model:unknown:intent") is not None
    monkeypatch.setattr(hive.ledger, "_post_write_fetch", original)
    with pytest.raises(LocalModelError, match="operation_already_recorded"):
        manager.change(hive, "unknown", "load", MODEL)
    assert not any(method == "POST" for method, _ in calls)


def test_unknown_load_cannot_be_reconciled_from_multiple_matching_instances(hive):
    manager, state, _ = server(fault="timeout_after_effect")
    with pytest.raises(LocalModelError):
        manager.change(hive, "ambiguous", "load", MODEL)
    state["models"][0]["loaded_instances"].append(loaded("another-instance"))
    assert manager.status(hive, "ambiguous")["status"] == "UNKNOWN"


def test_simultaneous_same_id_claims_only_one_post(hive):
    initial = inventory()
    barrier, lock = Barrier(2), Lock()
    count = [0, 0]
    state = inventory()

    def respond(request):
        if request.method == "GET":
            with lock:
                count[0] += 1
                first = count[0] <= 2
            if first:
                snapshot = copy.deepcopy(initial)
                barrier.wait(timeout=10)
                return httpx.Response(200, json=snapshot)
            return httpx.Response(200, json=state)
        with lock:
            count[1] += 1
        state["models"][0]["loaded_instances"] = [loaded()]
        return httpx.Response(
            200,
            json={
                "type": "llm",
                "status": "loaded",
                "instance_id": "fixture-instance",
                "load_config": {"context_length": 2048},
            },
        )

    def run(_):
        with Hive.open(hive.root) as reopened:
            manager = LMStudio(transport=httpx.MockTransport(respond))
            try:
                return manager.change(reopened, "same-id", "load", MODEL)["status"]
            except LocalModelError:
                return "refused"

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(run, [0, 1]))
    assert sorted(results) == ["PRODUCER_STATE_OBSERVED", "refused"]
    assert count[1] == 1


def test_lmstudio_schema_mode_records_exact_request_and_replays(hive, tmp_path, monkeypatch):
    monkeypatch.setenv("QUEEN_DISABLE_KEYRING", "1")
    monkeypatch.delenv("LMSTUDIO_API_KEY", raising=False)
    provider = build("lmstudio", SecretStore(tmp_path / "secrets"))
    assert provider.supports_structured_output
    assert not build("llamacpp", SecretStore(tmp_path / "secrets")).supports_structured_output
    provider.kind = "fixture"
    output = JsonSchemaOutput(
        {
            "type": "object",
            "properties": {"answer": {"type": "string"}},
            "required": ["answer"],
            "additionalProperties": False,
        }
    )
    request = InferenceRequest(
        "fixture-instance", (Message("user", "synthetic schema witness"),), max_tokens=16, output=output
    )
    cap = hive.authority().issue(
        "worker",
        "test",
        Grant(providers=("lmstudio",), models=("fixture-instance",), max_calls=1, max_output_tokens=16),
        60_000,
    )

    def respond(wire):
        body = json.loads(wire.content)
        assert body["response_format"]["json_schema"]["strict"] is True
        assert body["response_format"]["json_schema"]["schema"] == output.schema
        assert body["max_tokens"] == 16 and "tools" not in body
        return httpx.Response(
            200,
            json={
                "model": "fixture-instance",
                "choices": [{"message": {"content": '{"answer":"bee"}'}, "finish_reason": "stop"}],
            },
        )

    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        witnessed = Inference(hive, client).run(provider, request, actor="worker", capability=cap)
    assert witnessed.receipt.payload["provider_kind"] == "fixture"
    assert verify_receipt(hive, witnessed.receipt).text == '{"answer":"bee"}'


def test_cli_refuses_remote_lifecycle_without_private_error_output(capsys):
    assert main(["models", "list", "--base-url", "http://name:secret@example.com"]) == 2
    output = capsys.readouterr()
    assert "secret" not in output.err and "invalid_local_server_url" in output.err
