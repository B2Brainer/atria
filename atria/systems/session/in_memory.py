"""Sesiones en memoria, para desarrollar y testear sin BD.

Como en Postgres, una sesión existe desde que el sistema de información la crea; hasta
el primer `save` tiene el ciclo de vida por defecto.
"""

from atria.domain import InformationState, Session
from atria.systems.information import InformationError, InformationSystem
from atria.systems.session.interface import SessionError, SessionStore


class InMemorySessionStore(SessionStore):
    def __init__(self, information: InformationSystem) -> None:
        self._information = information
        self._sessions: dict[str, Session] = {}

    def save(self, session: Session) -> None:
        state = self._state(session.id)
        if state.purpose != session.purpose or state != session.state:
            raise SessionError(
                f"el propósito o el estado de la sesión '{session.id}' "
                "no coinciden con los almacenados"
            )
        self._sessions[session.id] = session.model_copy(deep=True)

    def get(self, session_id: str) -> Session:
        state = self._state(session_id)
        stored = self._sessions.get(session_id)
        if stored is None:
            return Session(id=session_id, purpose=state.purpose, state=state)
        return stored.model_copy(update={"state": state}, deep=True)

    def _state(self, session_id: str) -> InformationState:
        try:
            return self._information.get_state(session_id)
        except InformationError:
            raise SessionError(f"la sesión '{session_id}' no existe") from None
