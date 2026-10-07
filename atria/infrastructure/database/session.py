"""Almacenamiento de `Session` sobre PostgreSQL (p1 §5).

La fila de la sesión la crea `PostgresInformationSystem.create`; aquí se actualiza su
ciclo de vida según el contrato de `SessionStore`.
"""

from sqlalchemy import Connection, Engine, select, update

from atria.domain import Session
from atria.infrastructure.database import tables
from atria.infrastructure.database.information import load_state
from atria.systems.session import SessionError, SessionStore


class PostgresSessionStore(SessionStore):
    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def save(self, session: Session) -> None:
        with self._engine.begin() as conn:
            stored = self._load(conn, session.id, lock=True)
            if stored.purpose != session.purpose or stored.state != session.state:
                raise SessionError(
                    f"el propósito o el estado de la sesión '{session.id}' "
                    "no coinciden con los almacenados"
                )
            conn.execute(
                update(tables.session)
                .where(tables.session.c.id == session.id)
                .values(
                    status=session.status,
                    finish_reason=session.finish_reason,
                    max_iterations=session.max_iterations,
                )
            )

    def get(self, session_id: str) -> Session:
        with self._engine.connect() as conn:
            return self._load(conn, session_id)

    @staticmethod
    def _load(conn: Connection, session_id: str, lock: bool = False) -> Session:
        query = select(tables.session).where(tables.session.c.id == session_id)
        row = conn.execute(query.with_for_update() if lock else query).one_or_none()
        if row is None:
            raise SessionError(f"la sesión '{session_id}' no existe")
        return Session(
            id=row.id,
            purpose={"text": row.purpose},
            state=load_state(conn, session_id),
            status=row.status,
            finish_reason=row.finish_reason,
            max_iterations=row.max_iterations,
        )
