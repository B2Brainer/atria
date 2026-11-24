"""Record data models: an AI usage cycle and the interaction records it contains."""

from datetime import UTC, datetime
from uuid import UUID, uuid4

from pydantic import BaseModel, Field

from core.interaction.models import InteractionRequest, InteractionResult


class AIUsageCycle(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class InteractionRecord(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    cycle_id: UUID
    sequence: int
    request: InteractionRequest
    result: InteractionResult | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
