"""Acceptance criterion 2 (interaction-side models): fields and cardinalities per the Data spec."""

from decimal import Decimal

import pytest
from core.interaction.models import (
    ExecutionMetrics,
    InteractionRequest,
    InteractionResult,
    ProviderConfiguration,
)
from pydantic import ValidationError


def test_interaction_request_requires_its_fields():
    request = InteractionRequest(
        input="hello", provider_id="anthropic", model_id="claude", parameters={"temperature": 0.2}
    )
    assert request.input == "hello"
    assert request.provider_id == "anthropic"
    assert request.model_id == "claude"
    assert request.parameters == {"temperature": 0.2}


def test_interaction_request_missing_required_field_fails_validation():
    with pytest.raises(ValidationError):
        InteractionRequest(provider_id="anthropic", model_id="claude")


def test_execution_metrics_fields():
    metrics = ExecutionMetrics(
        input_tokens=10, output_tokens=20, duration=1.5, cost=Decimal("0.003")
    )
    assert metrics.input_tokens == 10
    assert metrics.output_tokens == 20
    assert metrics.duration == 1.5
    assert metrics.cost == Decimal("0.003")


def test_interaction_result_metrics_is_optional():
    result = InteractionResult(output="hi", status="success")
    assert result.metrics is None

    result_with_metrics = InteractionResult(
        output="hi",
        status="success",
        metrics=ExecutionMetrics(input_tokens=1, output_tokens=1, duration=0.1, cost=Decimal("0")),
    )
    assert result_with_metrics.metrics is not None


def test_interaction_result_missing_required_field_fails_validation():
    with pytest.raises(ValidationError):
        InteractionResult(status="success")


def test_provider_configuration_fields():
    config = ProviderConfiguration(
        provider_id="anthropic", endpoint="https://api.anthropic.com", credential_reference="ref-1"
    )
    assert config.provider_id == "anthropic"
    assert config.endpoint == "https://api.anthropic.com"
    assert config.credential_reference == "ref-1"
