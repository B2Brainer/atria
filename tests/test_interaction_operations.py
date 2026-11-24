"""Acceptance criteria 3, 4: InteractionManagement.initiate() against fakes for all three ports."""

from uuid import uuid4

from core.interaction.models import InteractionRequest, InteractionResult
from core.interaction.operations import InteractionManagement
from core.records.operations import InteractionRecordManagement
from tests.fakes import FakeAIProviderPort, FakeCredentialPort, FakePersistencePort


def _request() -> InteractionRequest:
    return InteractionRequest(input="hi", provider_id="anthropic", model_id="claude")


def test_initiate_returns_a_record_matching_the_request_and_provider_result():
    expected_result = InteractionResult(output="hello back", status="success")
    provider = FakeAIProviderPort(expected_result)
    credentials = FakeCredentialPort()
    records = InteractionRecordManagement(FakePersistencePort())
    interaction = InteractionManagement(uuid4(), provider, credentials, records)
    request = _request()

    record = interaction.initiate(request)

    assert record.request.input == request.input
    assert record.result == expected_result


def test_initiate_fetches_the_credential_before_invoking_the_provider():
    call_log: list[str] = []
    provider = FakeAIProviderPort(InteractionResult(output="ok", status="success"), call_log)
    credentials = FakeCredentialPort(call_log)
    records = InteractionRecordManagement(FakePersistencePort())
    interaction = InteractionManagement(uuid4(), provider, credentials, records)

    interaction.initiate(_request())

    # A shared call log across both fakes is what actually proves ORDER, not just
    # that each was called: asserting get_calls/received_requests independently
    # (as before) passes even if execute() ran before credentials.get().
    assert call_log == ["credentials.get", "provider.execute"]
    assert credentials.get_calls == ["anthropic"]
    assert len(provider.received_requests) == 1


def test_initiate_registers_the_assembled_record_with_record_management():
    provider = FakeAIProviderPort(InteractionResult(output="ok", status="success"))
    credentials = FakeCredentialPort()
    persistence = FakePersistencePort()
    records = InteractionRecordManagement(persistence)
    cycle_id = uuid4()
    interaction = InteractionManagement(cycle_id, provider, credentials, records)

    record = interaction.initiate(_request())

    assert persistence.get(record.id) == record
    assert record.cycle_id == cycle_id


def test_successive_initiate_calls_assign_increasing_sequence_within_the_cycle():
    provider = FakeAIProviderPort(InteractionResult(output="ok", status="success"))
    credentials = FakeCredentialPort()
    records = InteractionRecordManagement(FakePersistencePort())
    interaction = InteractionManagement(uuid4(), provider, credentials, records)

    first = interaction.initiate(_request())
    second = interaction.initiate(_request())

    assert first.sequence == 1
    assert second.sequence == 2
