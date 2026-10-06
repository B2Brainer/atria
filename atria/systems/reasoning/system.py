"""Sistema de razonamiento v0: reglas explícitas y deterministas, sin IA (p1 §3; t1 §2).

Decide el siguiente paso, evalúa cada resultado de IA y decide si el ciclo sigue.
Comparación de textos v0: dos textos dicen lo mismo si tienen las mismas palabras
(minúsculas, sin puntuación); se contradicen si coinciden al quitar las palabras
"no" y el número de "no" de cada uno tiene distinta paridad.

Criterio de evaluación provisional (gap G1):
- Toda información nueva de la IA entra como `UNVERIFIED`, nunca como `ACCEPTED`.
- Promoción a `ACCEPTED` por consenso: si un resultado repite una información no
  verificada, se promueve. Configurable con `promote_on_repetition`; con `False`
  nada se promueve automáticamente.
- Requiere validación la información que contradice conocimiento aceptado: no se
  promueve, se abre la pregunta `validate-<id>` y el veredicto es `NEEDS_VALIDATION`.
- Un resultado vacío se rechaza (`REJECT`) sin cambios.

Criterio de finalización provisional (gap G2): el propósito se cumple cuando hay al
menos un conocimiento aceptado durante el ciclo (`iteration >= 1`) y no quedan
preguntas abiertas. `max_iterations` es obligatorio y siempre acota el ciclo.
"""

import re
from collections.abc import Sequence

from atria.domain import (
    ActionType,
    AIResult,
    ChangeKind,
    Decision,
    EpistemicStatus,
    Evaluation,
    FinishReason,
    InformationItem,
    InformationState,
    IterationTrace,
    OpenQuestion,
    Origin,
    StateChange,
    Verdict,
)


class ReasoningSystem:
    def __init__(self, max_iterations: int, promote_on_repetition: bool = True) -> None:
        if max_iterations < 1:
            raise ValueError("max_iterations debe ser al menos 1")
        self._max_iterations = max_iterations
        self._promote_on_repetition = promote_on_repetition

    def next_step(self, state: InformationState) -> Decision:
        """Prioridad: pregunta abierta, luego verificar lo no verificado, luego explorar."""
        purpose = f"Propósito: {state.purpose.text}."
        question = _pending_question(state)
        if question is not None:
            return Decision(
                action=ActionType.ANSWER_QUESTION,
                instruction=f"{purpose} Responde a la pregunta abierta: {question.text}",
            )
        if state.unverified:
            return Decision(
                action=ActionType.VERIFY,
                instruction=f"{purpose} Confirma o corrige: «{state.unverified[0].content}»",
            )
        return Decision(
            action=ActionType.EXPLORE,
            instruction=f"{purpose} Aporta información nueva y relevante para cumplirlo.",
        )

    def evaluate(
        self, state: InformationState, result: AIResult, iteration: int
    ) -> Evaluation:
        """Propone los cambios de un resultado según el criterio v0 (G1).

        `iteration` es la iteración en curso (>= 1): la del item nuevo y su id.
        """
        if iteration < 1:
            raise ValueError("iteration debe ser al menos 1")
        content = result.content.strip()
        if not content:
            return Evaluation(verdict=Verdict.REJECT)

        changes = []
        question = _pending_question(state)
        if question is not None:
            changes.append(
                StateChange(kind=ChangeKind.CLOSE_QUESTION, target_id=question.id)
            )

        words = _words(content)
        existing = next((i for i in state.items if _words(i.content) == words), None)
        conflict = next(
            (i for i in state.accepted if _contradicts(_words(i.content), words)), None
        )
        if existing is None:
            existing = InformationItem(
                id=f"ai-{iteration}",
                content=content,
                status=EpistemicStatus.UNVERIFIED,
                origin=Origin.AI,
                iteration=iteration,
            )
            changes.append(StateChange(kind=ChangeKind.ADD_INFORMATION, item=existing))
        elif (
            existing.status == EpistemicStatus.UNVERIFIED
            and self._promote_on_repetition
            and conflict is None
        ):
            changes.append(StateChange(kind=ChangeKind.PROMOTE, target_id=existing.id))

        if conflict is None:
            return Evaluation(verdict=Verdict.ACCEPT, changes=changes)
        question_id = f"validate-{existing.id}"
        if all(q.id != question_id for q in state.questions):
            text = f"«{content}» contradice el conocimiento aceptado «{conflict.content}». ¿Cuál es correcto?"
            changes.append(
                StateChange(
                    kind=ChangeKind.OPEN_QUESTION,
                    question=OpenQuestion(id=question_id, text=text),
                )
            )
        return Evaluation(verdict=Verdict.NEEDS_VALIDATION, changes=changes)

    def should_continue(
        self, state: InformationState, history: Sequence[IterationTrace]
    ) -> tuple[bool, FinishReason | None]:
        """Devuelve `(True, None)` o `(False, motivo)`; el propósito cumplido prevalece."""
        if not state.open_questions and any(i.iteration >= 1 for i in state.accepted):
            return False, FinishReason.PURPOSE_FULFILLED
        if len(history) >= self._max_iterations:
            return False, FinishReason.MAX_ITERATIONS
        return True, None


def _pending_question(state: InformationState) -> OpenQuestion | None:
    """La pregunta que `next_step` manda responder y que `evaluate` cierra."""
    return next(iter(state.open_questions), None)


def _words(text: str) -> list[str]:
    return re.findall(r"\w+", text.lower())


def _contradicts(a: list[str], b: list[str]) -> bool:
    def without_no(words: list[str]) -> list[str]:
        return [w for w in words if w != "no"]

    return without_no(a) == without_no(b) and (a.count("no") - b.count("no")) % 2 == 1
