"""Retrospectiva final que se entrega al usuario (p1 §1; t1 §6).

Contenido v0 provisional (gap G6). Se construye de forma determinista a partir de la
sesión terminada y sus trazas, sin IA: con las mismas entradas da el mismo resultado.
"""

from collections.abc import Sequence

from pydantic import BaseModel, Field

from atria.domain.information import InformationItem, NonEmptyStr, OpenQuestion, Purpose
from atria.domain.reasoning import Decision, StateChange
from atria.domain.session import CycleStatus, FinishReason, IterationTrace, Session


class IterationSummary(BaseModel):
    iteration: int = Field(ge=1)
    decision: Decision
    applied_changes: list[StateChange]


class Retrospective(BaseModel):
    session_id: NonEmptyStr
    purpose: Purpose
    iterations: int = Field(ge=0)
    finish_reason: FinishReason
    accepted_knowledge: list[InformationItem]
    unverified: list[InformationItem]
    open_questions: list[OpenQuestion]
    summary: list[IterationSummary]


def build_retrospective(
    session: Session, traces: Sequence[IterationTrace]
) -> Retrospective:
    """Construye la retrospectiva de una sesión terminada a partir de sus trazas.

    Lanza `ValueError` si la sesión no terminó o si las trazas no son las de la
    sesión: de otra sesión, no consecutivas desde 1, o sin acabar en su estado final.
    """
    if session.status != CycleStatus.FINISHED or session.finish_reason is None:
        raise ValueError(f"la sesión '{session.id}' no ha terminado")
    if any(t.session_id != session.id for t in traces):
        raise ValueError(f"hay trazas que no son de la sesión '{session.id}'")
    if [t.iteration for t in traces] != list(range(1, len(traces) + 1)):
        raise ValueError("las trazas no son consecutivas desde la iteración 1")
    if traces and traces[-1].resulting_state != session.state:
        raise ValueError("la última traza no acaba en el estado final de la sesión")

    state = session.state
    return Retrospective(
        session_id=session.id,
        purpose=session.purpose,
        iterations=len(traces),
        finish_reason=session.finish_reason,
        accepted_knowledge=state.accepted,
        unverified=state.unverified,
        open_questions=state.open_questions,
        summary=[
            IterationSummary(
                iteration=t.iteration,
                decision=t.decision,
                applied_changes=t.applied_changes,
            )
            for t in traces
        ],
    )
