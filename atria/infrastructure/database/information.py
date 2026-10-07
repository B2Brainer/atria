"""Sistema de información sobre PostgreSQL (p1 §3, §5).

Las reglas de transición son las de `apply_change`, compartidas con la
implementación en memoria. `apply` bloquea la fila de la sesión, aplica los cambios
sobre una copia del estado y solo entonces reescribe items y preguntas, todo en una
transacción: o se guardan todos los cambios o ninguno.
"""

from sqlalchemy import Connection, Engine, delete, insert, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert

from atria.domain import CycleStatus, Evaluation, InformationState, Purpose, StateChange
from atria.infrastructure.database import tables
from atria.systems.information import InformationError, InformationSystem, apply_change


class PostgresInformationSystem(InformationSystem):
    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def create(self, session_id: str, purpose: Purpose) -> InformationState:
        state = InformationState(purpose=purpose)
        with self._engine.begin() as conn:
            created = conn.execute(
                pg_insert(tables.session)
                .values(
                    id=session_id,
                    purpose=purpose.text,
                    status=CycleStatus.RUNNING,
                    finish_reason=None,
                    questions=[],
                )
                .on_conflict_do_nothing()
                .returning(tables.session.c.id)
            ).first()
        # `rowcount` no sirve aquí: psycopg devuelve -1 con ON CONFLICT DO NOTHING.
        if created is None:
            raise InformationError(f"la sesión '{session_id}' ya existe")
        return state

    def get_state(self, session_id: str) -> InformationState:
        with self._engine.connect() as conn:
            return load_state(conn, session_id)

    def apply(self, session_id: str, evaluation: Evaluation) -> list[StateChange]:
        with self._engine.begin() as conn:
            state = load_state(conn, session_id, lock=True)
            applied = [change.model_copy(deep=True) for change in evaluation.changes]
            for change in applied:
                apply_change(state, change)
            _write_state(conn, session_id, state)
        return applied


def load_state(
    conn: Connection, session_id: str, lock: bool = False
) -> InformationState:
    query = select(tables.session).where(tables.session.c.id == session_id)
    row = conn.execute(query.with_for_update() if lock else query).one_or_none()
    if row is None:
        raise InformationError(f"la sesión '{session_id}' no existe")
    items = conn.execute(
        select(tables.information_item)
        .where(tables.information_item.c.session_id == session_id)
        .order_by(tables.information_item.c.position)
    ).mappings()
    return InformationState.model_validate(
        {
            "purpose": {"text": row.purpose},
            "items": [dict(item) for item in items],
            "questions": row.questions,
        }
    )


def _write_state(conn: Connection, session_id: str, state: InformationState) -> None:
    items = tables.information_item
    conn.execute(delete(items).where(items.c.session_id == session_id))
    if state.items:
        conn.execute(
            insert(items),
            [
                {"session_id": session_id, "position": position, **item.model_dump()}
                for position, item in enumerate(state.items)
            ],
        )
    conn.execute(
        update(tables.session)
        .where(tables.session.c.id == session_id)
        .values(questions=[q.model_dump(mode="json") for q in state.questions])
    )
