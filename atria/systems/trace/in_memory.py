"""Registro de trazas en memoria, para desarrollar y testear el ciclo sin BD."""

from atria.domain import IterationTrace
from atria.systems.trace.interface import TraceError, TraceRecorder


class InMemoryTraceRecorder(TraceRecorder):
    def __init__(self) -> None:
        self._traces: dict[str, list[IterationTrace]] = {}

    def record(self, trace: IterationTrace) -> None:
        # Revalida y copia a la vez: detecta trazas creadas con `model_construct` o
        # mutadas tras construirse, y aísla lo almacenado del objeto del llamador.
        stored = IterationTrace.model_validate(trace.model_dump())
        expected = len(self._traces.get(stored.session_id, [])) + 1
        if stored.iteration != expected:
            raise TraceError(
                f"la sesión '{stored.session_id}' espera la iteración {expected}, "
                f"no la {stored.iteration}"
            )
        self._traces.setdefault(stored.session_id, []).append(stored)

    def list(self, session_id: str) -> list[IterationTrace]:
        return [t.model_copy(deep=True) for t in self._traces.get(session_id, [])]
