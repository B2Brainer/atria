"""Ciclo mínimo de Atria, explícito y sin frameworks externos (p1 §1, §3, §9; t1 §6).

Cada iteración: estado → decisión → uso de IA → evaluación → aplicación → traza.
El orquestador solo conoce los sistemas de `atria.systems`; las implementaciones
concretas se le inyectan.

Fallos: un `AIProviderError` termina la sesión con `error` antes de aplicar nada,
así que el estado y las trazas quedan como tras la última iteración completa, y
también hay retrospectiva. Cualquier otro error es un defecto del sistema y se propaga.
"""

from atria.domain import (
    CycleStatus,
    FinishReason,
    IterationTrace,
    Retrospective,
    Session,
    build_retrospective,
)
from atria.systems.ai import AIProviderError, AISystem
from atria.systems.information import InformationSystem
from atria.systems.reasoning import ReasoningSystem
from atria.systems.trace import TraceRecorder


class Orchestrator:
    def __init__(
        self,
        information: InformationSystem,
        reasoning: ReasoningSystem,
        ai: AISystem,
        trace: TraceRecorder,
    ) -> None:
        self._information = information
        self._reasoning = reasoning
        self._ai = ai
        self._trace = trace

    def run(self, session: Session) -> tuple[Session, Retrospective]:
        """Ejecuta el ciclo hasta que termina.

        Devuelve la sesión terminada (con su motivo de finalización) y la
        retrospectiva final que se entrega al usuario.

        El estado de la sesión debe existir ya en el sistema de información.
        """
        if session.status != CycleStatus.RUNNING:
            raise ValueError(f"la sesión '{session.id}' ya terminó")
        history = self._trace.list(session.id)
        while True:
            state = self._information.get_state(session.id)
            should_continue, reason = self._reasoning.should_continue(state, history)
            if not should_continue:
                break
            iteration = len(history) + 1
            decision = self._reasoning.next_step(state)
            request = self._ai.build_request(decision, state)
            try:
                result = self._ai.execute(decision, state)
            except AIProviderError:
                reason = FinishReason.ERROR
                break
            evaluation = self._reasoning.evaluate(state, result, iteration)
            applied = self._information.apply(session.id, evaluation)
            trace = IterationTrace(
                session_id=session.id,
                iteration=iteration,
                previous_state=state,
                decision=decision,
                ai_request=request,
                ai_result=result,
                evaluation=evaluation,
                applied_changes=applied,
                resulting_state=self._information.get_state(session.id),
            )
            self._trace.record(trace)
            history.append(trace)

        finished = Session(
            id=session.id,
            purpose=session.purpose,
            state=self._information.get_state(session.id),
            status=CycleStatus.FINISHED,
            finish_reason=reason,
        )
        return finished, build_retrospective(finished, history)
