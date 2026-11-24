"""Interaction data models: a request to an AI provider and the result it returns."""

from decimal import Decimal

from pydantic import BaseModel


class ProviderConfiguration(BaseModel):
    provider_id: str
    endpoint: str
    credential_reference: str


class InteractionRequest(BaseModel):
    input: str
    provider_id: str
    model_id: str
    parameters: dict = {}


class ExecutionMetrics(BaseModel):
    input_tokens: int
    output_tokens: int
    duration: float
    cost: Decimal


class InteractionResult(BaseModel):
    output: str
    status: str
    metrics: ExecutionMetrics | None = None
