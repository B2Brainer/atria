"""Acceptance criteria 5, 6, 7, 8: InteractionRecordManagement against a fake PersistencePort."""

from uuid import uuid4

from core.interaction.models import InteractionRequest
from core.records.models import InteractionRecord
from core.records.operations import InteractionRecordManagement
from tests.fakes import FakePersistencePort


def _request() -> InteractionRequest:
    return InteractionRequest(input="hi", provider_id="anthropic", model_id="claude")


def test_register_interaction_saves_the_record_exactly_once():
    persistence = FakePersistencePort()
    records = InteractionRecordManagement(persistence)
    cycle_id = uuid4()
    record = InteractionRecord(cycle_id=cycle_id, sequence=1, request=_request())

    records._register_interaction(record)

    assert persistence.get(record.id) == record
    assert len(persistence.list_by_cycle(cycle_id)) == 1


def test_get_returns_the_persisted_record():
    persistence = FakePersistencePort()
    records = InteractionRecordManagement(persistence)
    record = InteractionRecord(cycle_id=uuid4(), sequence=1, request=_request())
    persistence.save(record)

    assert records.get(record.id) == record


def test_list_by_cycle_returns_records_ordered_by_sequence_even_when_unordered():
    persistence = FakePersistencePort()
    records = InteractionRecordManagement(persistence)
    cycle_id = uuid4()
    third = InteractionRecord(cycle_id=cycle_id, sequence=3, request=_request())
    first = InteractionRecord(cycle_id=cycle_id, sequence=1, request=_request())
    second = InteractionRecord(cycle_id=cycle_id, sequence=2, request=_request())
    persistence.save(third)
    persistence.save(first)
    persistence.save(second)

    result = records.list_by_cycle(cycle_id)

    assert [record.sequence for record in result] == [1, 2, 3]


def test_assign_sequence_is_strictly_increasing_within_a_cycle():
    persistence = FakePersistencePort()
    records = InteractionRecordManagement(persistence)
    cycle_id = uuid4()

    first_sequence = records._assign_sequence(cycle_id)
    persistence.save(
        InteractionRecord(cycle_id=cycle_id, sequence=first_sequence, request=_request())
    )
    second_sequence = records._assign_sequence(cycle_id)
    persistence.save(
        InteractionRecord(cycle_id=cycle_id, sequence=second_sequence, request=_request())
    )
    third_sequence = records._assign_sequence(cycle_id)

    assert first_sequence == 1
    assert second_sequence == 2
    assert third_sequence == 3


def test_assign_sequence_is_scoped_per_cycle():
    persistence = FakePersistencePort()
    records = InteractionRecordManagement(persistence)
    other_cycle = uuid4()
    persistence.save(InteractionRecord(cycle_id=other_cycle, sequence=5, request=_request()))

    assert records._assign_sequence(uuid4()) == 1
