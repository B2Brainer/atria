"""Acceptance criteria 1, 2, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15: `api/`'s seven operations."""

import json
import sys
import uuid

import pytest

if sys.platform != "darwin":
    pytest.skip(
        "api/'s composition wires a real CredentialAdapter (darwin only); see conftest.py.",
        allow_module_level=True,
    )

from api.handlers import dispatch_table
from api.rpc import RpcDispatcher
from core.interaction.models import ExecutionMetrics, InteractionResult
from tests.fakes import FakeAIProviderPort


def test_dispatch_table_covers_exactly_the_seven_operations(handlers):
    from api.handlers import OPERATIONS

    table = dispatch_table(handlers)

    assert set(table.keys()) == set(OPERATIONS)
    assert all(callable(fn) for fn in table.values())


def test_composition_wires_real_adapters(composition):
    from adapters.credentials.adapter import CredentialAdapter
    from adapters.persistence.adapter import PersistenceAdapter
    from adapters.providers.adapter import AIProviderAdapter

    assert isinstance(composition.credentials, CredentialAdapter)
    assert isinstance(composition.persistence, PersistenceAdapter)
    assert isinstance(composition.provider_adapter, AIProviderAdapter)


def test_initiate_reaches_core_and_returns_serialized_record(handlers, composition):
    handlers.set_credential("openai", "test-value")
    fake_provider = FakeAIProviderPort(
        InteractionResult(
            output="hi",
            status="success",
            metrics=ExecutionMetrics(input_tokens=1, output_tokens=2, duration=0.1, cost="0.01"),
        )
    )
    composition.provider_adapter = fake_provider
    cycle_id = str(uuid.uuid4())

    record = handlers.initiate(
        {"input": "hello", "provider_id": "openai", "model_id": "gpt-4o-mini", "parameters": {}},
        cycle_id,
    )

    assert record["result"]["output"] == "hi"
    assert record["result"]["metrics"]["input_tokens"] == 1
    assert fake_provider.received_requests[0].input == "hello"
    assert record["cycle_id"] == cycle_id


def test_initiate_with_result_metrics_none_serializes_as_none(handlers, composition):
    handlers.set_credential("openai", "test-value")
    fake_provider = FakeAIProviderPort(
        InteractionResult(output="hi", status="success", metrics=None)
    )
    composition.provider_adapter = fake_provider

    record = handlers.initiate(
        {"input": "hello", "provider_id": "openai", "model_id": "gpt-4o-mini", "parameters": {}},
        str(uuid.uuid4()),
    )

    assert record["result"]["metrics"] is None


def test_get_and_list_by_cycle_round_trip(handlers, composition):
    handlers.set_credential("openai", "test-value")
    fake_provider = FakeAIProviderPort(InteractionResult(output="hi", status="success"))
    composition.provider_adapter = fake_provider
    cycle_id = str(uuid.uuid4())
    record = handlers.initiate(
        {"input": "hello", "provider_id": "openai", "model_id": "gpt-4o-mini", "parameters": {}},
        cycle_id,
    )

    fetched = handlers.get(record["id"])
    listed = handlers.list_by_cycle(cycle_id)

    assert fetched == record
    assert listed == [record]


def test_list_cycles_discovers_new_conversation_only_after_first_save(handlers, composition):
    assert handlers.list_cycles() == []
    handlers.set_credential("openai", "test-value")

    fake_provider = FakeAIProviderPort(InteractionResult(output="hi", status="success"))
    composition.provider_adapter = fake_provider
    cycle_id = str(uuid.uuid4())
    handlers.initiate(
        {"input": "hello", "provider_id": "openai", "model_id": "gpt-4o-mini", "parameters": {}},
        cycle_id,
    )

    assert handlers.list_cycles() == [cycle_id]


def test_set_get_status_and_remove_credential_round_trip(handlers):
    status_before = handlers.get_credential_status("openai")
    assert status_before == {
        "configured": False,
        "status": "not_configured",
        "masked_preview": None,
    }

    handlers.set_credential("openai", "test-value-abcd1234")

    status_after = handlers.get_credential_status("openai")
    assert status_after["configured"] is True
    assert status_after["status"] == "configured"
    assert status_after["masked_preview"].endswith("1234")
    assert "test-value-abcd1234" not in status_after["masked_preview"]

    handlers.remove_credential("openai")

    assert handlers.get_credential_status("openai") == {
        "configured": False,
        "status": "not_configured",
        "masked_preview": None,
    }


def test_remove_credential_is_idempotent_when_not_configured(handlers):
    assert handlers.remove_credential("openai") == {"success": True}


def test_set_credential_never_returns_the_secret(handlers):
    result = handlers.set_credential("openai", "test-super-secret-value")

    assert result == {"success": True}
    assert "test-super-secret-value" not in str(result)


def test_set_credential_calls_store_exactly_once_with_the_unchanged_value(handlers, composition):
    calls: list[tuple[str, str]] = []
    original_store = composition.credentials.store

    def spying_store(reference: str, secret: str) -> None:
        calls.append((reference, secret))
        original_store(reference, secret)

    composition.credentials.store = spying_store

    handlers.set_credential("openai", "test-exact-once-value")

    expected_reference = composition.providers["openai"].credential_reference
    assert calls == [(expected_reference, "test-exact-once-value")]


SECRET = "test-wire-inspection-secret-value"


def _dispatch_over_the_wire(handlers) -> RpcDispatcher:
    return RpcDispatcher(dispatch_table(handlers))


def test_full_credentialed_initiate_round_trip_never_puts_the_secret_on_the_wire(
    handlers, composition
):
    dispatcher = _dispatch_over_the_wire(handlers)
    dispatcher.dispatch(
        {"id": 1, "method": "set_credential", "params": {"provider_id": "openai", "secret": SECRET}}
    )

    composition.provider_adapter = FakeAIProviderPort(
        InteractionResult(
            output="hi",
            status="success",
            metrics=ExecutionMetrics(input_tokens=1, output_tokens=2, duration=0.1, cost="0.01"),
        )
    )
    cycle_id = str(uuid.uuid4())

    initiate_response = dispatcher.dispatch(
        {
            "id": 2,
            "method": "initiate",
            "params": {
                "request": {
                    "input": "hello",
                    "provider_id": "openai",
                    "model_id": "gpt-4o-mini",
                    "parameters": {},
                },
                "cycle_id": cycle_id,
            },
        }
    )
    get_response = dispatcher.dispatch(
        {"id": 3, "method": "get", "params": {"record_id": initiate_response["result"]["id"]}}
    )
    list_response = dispatcher.dispatch(
        {"id": 4, "method": "list_by_cycle", "params": {"cycle_id": cycle_id}}
    )

    for response in (initiate_response, get_response, list_response):
        wire_text = json.dumps(response)
        assert SECRET not in wire_text
        assert "Bearer" not in wire_text


def test_credential_status_and_remove_payloads_never_put_the_secret_on_the_wire(
    handlers, composition
):
    dispatcher = _dispatch_over_the_wire(handlers)
    dispatcher.dispatch(
        {"id": 1, "method": "set_credential", "params": {"provider_id": "openai", "secret": SECRET}}
    )

    status_response = dispatcher.dispatch(
        {"id": 2, "method": "get_credential_status", "params": {"provider_id": "openai"}}
    )
    remove_response = dispatcher.dispatch(
        {"id": 3, "method": "remove_credential", "params": {"provider_id": "openai"}}
    )

    for response in (status_response, remove_response):
        assert SECRET not in json.dumps(response)
