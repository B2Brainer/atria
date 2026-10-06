"""Sesión y trazabilidad por iteración (p1 §4)."""

from datetime import UTC, datetime
from enum import StrEnum

from pydantic import AwareDatetime, BaseModel, Field, model_validator

from atria.domain.ai import AIRequest, AIResult
from atria.domain.information import InformationState, NonEmptyStr, Purpose
from atria.domain.reasoning import Decision, Evaluation, StateChange


class IterationTrace(BaseModel):
    """Los 7 campos observables de una iteración (p1 §4). Todos obligatorios.

    Se identifica por sesión e iteración (desde 1). No incluye el razonamiento
    interno privado del modelo (p1 §4).
    """

    session_id: NonEmptyStr
    iteration: int = Field(ge=1)
    timestamp: AwareDatetime = Field(default_factory=lambda: datetime.now(UTC))
    previous_state: InformationState
    decision: Decision
    ai_request: AIRequest
    ai_result: AIResult
    evaluation: Evaluation
    applied_changes: list[StateChange]
    resulting_state: InformationState


class CycleStatus(StrEnum):
    RUNNING = "running"
    FINISHED = "finished"


class FinishReason(StrEnum):
    PURPOSE_FULFILLED = "purpose_fulfilled"
    MAX_ITERATIONS = "max_iterations"
    ERROR = "error"


class Session(BaseModel):
    id: NonEmptyStr
    purpose: Purpose
    state: InformationState
    status: CycleStatus = CycleStatus.RUNNING
    finish_reason: FinishReason | None = None

    @model_validator(mode="after")
    def _consistent(self) -> "Session":
        if (self.status == CycleStatus.FINISHED) != (self.finish_reason is not None):
            raise ValueError("finish_reason se informa si y solo si la sesión terminó")
        if self.state.purpose != self.purpose:
            raise ValueError("el propósito del estado no coincide con el de la sesión")
        return self
