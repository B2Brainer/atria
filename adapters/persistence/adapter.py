"""PersistenceAdapter — implements PersistencePort against a local SQLite database.

Public contract (per the Interfaces specification): ``save()``, ``get()``,
``list_by_cycle()``. ``_serialize_record()`` and ``_deserialize_record()`` are
internal, invoked only from those public operations.
"""

from __future__ import annotations

from pathlib import Path
from uuid import UUID

from alembic import command
from alembic.config import Config
from core.ports.persistence import PersistencePort
from core.records.models import InteractionRecord
from sqlalchemy import create_engine, select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from adapters.persistence.models import InteractionRecordRow

_DEFAULT_MIGRATIONS_DIR = Path(__file__).resolve().parent / "migrations"


class PersistenceAdapter(PersistencePort):
    def __init__(self, db_path: str, migrations_dir: Path | str | None = None) -> None:
        self._db_path = db_path
        self._migrations_dir = Path(migrations_dir) if migrations_dir else _DEFAULT_MIGRATIONS_DIR
        self._engine = create_engine(f"sqlite:///{db_path}")
        self._run_migrations()

    def _run_migrations(self) -> None:
        config = Config()
        config.set_main_option("script_location", str(self._migrations_dir))
        config.set_main_option("sqlalchemy.url", f"sqlite:///{self._db_path}")
        command.upgrade(config, "head")

    def _serialize_record(self, record: InteractionRecord) -> str:
        return record.model_dump_json()

    def _deserialize_record(self, payload: str) -> InteractionRecord:
        return InteractionRecord.model_validate_json(payload)

    def save(self, record: InteractionRecord) -> None:
        payload = self._serialize_record(record)
        stmt = sqlite_insert(InteractionRecordRow).values(
            id=str(record.id),
            cycle_id=str(record.cycle_id),
            sequence=record.sequence,
            payload=payload,
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=[InteractionRecordRow.id],
            set_={
                "cycle_id": str(record.cycle_id),
                "sequence": record.sequence,
                "payload": payload,
            },
        )
        with Session(self._engine) as session:
            session.execute(stmt)
            session.commit()

    def get(self, record_id: UUID) -> InteractionRecord:
        with Session(self._engine) as session:
            row = session.execute(
                select(InteractionRecordRow).where(InteractionRecordRow.id == str(record_id))
            ).scalar_one()
            return self._deserialize_record(row.payload)

    def list_by_cycle(self, cycle_id: UUID) -> list[InteractionRecord]:
        with Session(self._engine) as session:
            rows = session.execute(
                select(InteractionRecordRow).where(
                    InteractionRecordRow.cycle_id == str(cycle_id)
                )
            ).scalars()
            return [self._deserialize_record(row.payload) for row in rows]
