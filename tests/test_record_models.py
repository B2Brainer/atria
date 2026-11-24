"""Acceptance criterion 2 (record-side models): AIUsageCycle / InteractionRecord cardinalities."""

from uuid import uuid4

import pytest
from core.interaction.models import InteractionRequest, InteractionResult
from core.records.models import AIUsageCycle, InteractionRecord
from pydantic import ValidationError


def _request() -> InteractionRequest:
    return InteractionRequest(input="hi", provider_id="anthropic", model_id="claude")


def test_ai_usage_cycle_has_id_and_created_at():
    cycle = AIUsageCycle()
    assert cycle.id is not None
    assert cycle.created_at is not None


def test_interaction_record_requires_a_request():
    with pytest.raises(ValidationError):
        InteractionRecord(cycle_id=uuid4(), sequence=1)


def test_interaction_record_result_is_optional():
    record = InteractionRecord(cycle_id=uuid4(), sequence=1, request=_request())
    assert record.result is None


def test_interaction_record_accepts_a_result():
    record = InteractionRecord(
        cycle_id=uuid4(),
        sequence=1,
        request=_request(),
        result=InteractionResult(output="hi", status="success"),
    )
    assert record.result is not None
    assert record.result.output == "hi"
