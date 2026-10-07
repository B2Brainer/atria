"""API HTTP de Atria (p1 §5 "FastAPI").

Solo traduce HTTP ↔ dominio: delega en el orquestador y en las interfaces de
`atria.systems`, que se le inyectan. Errores: 404 si la sesión no existe, 409 si la
operación no aplica a su ciclo de vida, 422 si la entrada no es válida, y cualquier
otro fallo es 500 con un cuerpo genérico; el detalle solo va al log del servidor.
"""

import logging
import threading
import uuid
from typing import Annotated

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from atria.domain import (
    CycleStatus,
    IterationTrace,
    Purpose,
    Retrospective,
    Session,
    build_retrospective,
)
from atria.domain.information import NonEmptyStr
from atria.orchestration import Orchestrator
from atria.systems.ai import AIProvider, AISystem
from atria.systems.information import InformationSystem
from atria.systems.reasoning import ReasoningSystem
from atria.systems.session import SessionError, SessionStore
from atria.systems.trace import TraceRecorder

logger = logging.getLogger(__name__)


class SessionCreated(BaseModel):
    session_id: str


def create_app(
    information: InformationSystem,
    trace: TraceRecorder,
    sessions: SessionStore,
    provider: AIProvider,
    max_iterations: int,
) -> FastAPI:
    """`max_iterations` es el máximo configurado y el valor por defecto por sesión."""
    if max_iterations < 1:
        raise ValueError("max_iterations debe ser al menos 1")

    # Fuera del cuerpo de la clase: allí `max_iterations` sería el propio campo.
    MaxIterations = Annotated[int | None, Field(ge=1, le=max_iterations, strict=True)]

    class CreateSession(BaseModel):
        purpose: NonEmptyStr
        max_iterations: MaxIterations = None

    app = FastAPI(title="Atria")
    ai = AISystem(provider)
    # Sesiones con un ciclo en curso en este proceso: un reintento del cliente no debe
    # ejecutar el mismo ciclo dos veces en paralelo.
    running: set[str] = set()
    running_lock = threading.Lock()

    @app.exception_handler(Exception)
    def internal_error(request: Request, error: Exception) -> JSONResponse:
        logger.error(
            "error interno en %s %s",
            request.method,
            request.url.path,
            exc_info=error,
        )
        return JSONResponse(status_code=500, content={"detail": "error interno"})

    def get_session(session_id: str) -> Session:
        try:
            return sessions.get(session_id)
        except SessionError:
            raise HTTPException(404, "la sesión no existe") from None

    @app.post("/sessions", status_code=201)
    def create_session(body: CreateSession) -> SessionCreated:
        session_id = uuid.uuid4().hex
        state = information.create(session_id, Purpose(text=body.purpose))
        sessions.save(
            Session(
                id=session_id,
                purpose=state.purpose,
                state=state,
                max_iterations=body.max_iterations,
            )
        )
        return SessionCreated(session_id=session_id)

    @app.post("/sessions/{session_id}/run")
    def run_session(session_id: str) -> Retrospective:
        with running_lock:
            if session_id in running:
                raise HTTPException(409, "la sesión ya se está ejecutando")
            running.add(session_id)
        try:
            # Se lee tras reservarla: otra petición pudo terminarla justo antes.
            session = get_session(session_id)
            if session.status != CycleStatus.RUNNING:
                raise HTTPException(409, "la sesión ya terminó")
            reasoning = ReasoningSystem(session.max_iterations or max_iterations)
            orchestrator = Orchestrator(information, reasoning, ai, trace)
            finished, retrospective = orchestrator.run(session)
            sessions.save(finished)
            return retrospective
        finally:
            with running_lock:
                running.discard(session_id)

    @app.get("/sessions/{session_id}")
    def read_session(session_id: str) -> Session:
        return get_session(session_id)

    @app.get("/sessions/{session_id}/trace")
    def read_trace(session_id: str) -> list[IterationTrace]:
        get_session(session_id)
        return trace.list(session_id)

    @app.get("/sessions/{session_id}/retrospective")
    def read_retrospective(session_id: str) -> Retrospective:
        session = get_session(session_id)
        if session.status != CycleStatus.FINISHED:
            raise HTTPException(409, "la sesión no ha terminado")
        return build_retrospective(session, trace.list(session_id))

    return app
