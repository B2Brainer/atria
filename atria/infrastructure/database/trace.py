"""Registro de trazas sobre PostgreSQL (p1 §4, §5).

Cada traza es una fila `(session_id, iteration)` con su contenido completo en JSONB.
La clave primaria garantiza que dos registros concurrentes de la misma iteración no
se guarden ambos.
"""

from sqlalchemy import Engine, func, insert, select
from sqlalchemy.exc import IntegrityError

from atria.domain import IterationTrace
from atria.infrastructure.database import tables
from atria.systems.trace import TraceError, TraceRecorder


class PostgresTraceRecorder(TraceRecorder):
    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def record(self, trace: IterationTrace) -> None:
        # Revalida igual que la implementación en memoria (trazas creadas con
        # `model_construct` o mutadas tras construirse).
        stored = IterationTrace.model_validate(trace.model_dump())
        column = tables.iteration.c
        try:
            with self._engine.begin() as conn:
                last = conn.execute(
                    select(func.max(column.iteration)).where(
                        column.session_id == stored.session_id
                    )
                ).scalar_one()
                expected = (last or 0) + 1
                if stored.iteration != expected:
                    raise TraceError(
                        f"la sesión '{stored.session_id}' espera la iteración "
                        f"{expected}, no la {stored.iteration}"
                    )
                conn.execute(
                    insert(tables.iteration).values(
                        session_id=stored.session_id,
                        iteration=stored.iteration,
                        data=stored.model_dump(mode="json"),
                    )
                )
        except IntegrityError:
            # Otra transacción registró la misma iteración entre la lectura y el insert.
            raise TraceError(
                f"la iteración {stored.iteration} de la sesión "
                f"'{stored.session_id}' ya está registrada"
            ) from None

    def list(self, session_id: str) -> list[IterationTrace]:
        column = tables.iteration.c
        with self._engine.connect() as conn:
            rows = conn.execute(
                select(column.data)
                .where(column.session_id == session_id)
                .order_by(column.iteration)
            ).scalars()
            return [IterationTrace.model_validate(data) for data in rows]
