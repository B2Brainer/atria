"""PersistenceAdapter — implements PersistencePort against a local SQLite database.

Public contract (per the Interfaces specification): ``save()``, ``get()``,
``list_by_cycle()``. ``_serialize_record()`` and ``_deserialize_record()`` are
internal, invoked only from those public operations.
"""

from __future__ import annotations

import logging
import os
import time
from pathlib import Path
from uuid import UUID

from alembic import command
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from core.ports.persistence import PersistencePort
from core.records.models import InteractionRecord
from sqlalchemy import create_engine, select, text
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from adapters.persistence.models import InteractionRecordRow

_DEFAULT_MIGRATIONS_DIR = Path(__file__).resolve().parent / "migrations"

logger = logging.getLogger(__name__)


class PersistenceAdapter(PersistencePort):
    def __init__(self, db_path: str, migrations_dir: Path | str | None = None) -> None:
        self._db_path = db_path
        self._migrations_dir = Path(migrations_dir) if migrations_dir else _DEFAULT_MIGRATIONS_DIR
        self._engine = create_engine(f"sqlite:///{db_path}")
        self._run_migrations()
        self._restrict_file_permissions()

    def _restrict_file_permissions(self) -> None:
        # Interaction records are local-only but unencrypted at rest; restrict
        # the file to the owner (0600) rather than leaving it at the process
        # umask default. No-op for ":memory:" (no file exists).
        if self._db_path == ":memory:" or not os.path.exists(self._db_path):
            return
        os.chmod(self._db_path, 0o600)

    def _run_migrations(self) -> None:
        # Drive Alembic off this adapter's own connection (config.attributes,
        # read by migrations/env.py) rather than a second engine built from a
        # `sqlalchemy.url` string. Avoids two real bugs a URL-string approach
        # has: a ":memory:" db_path would give the migration engine and
        # self._engine two independent, unconnected in-memory databases; and
        # ConfigParser interpolates "%" in set_main_option values; db_path no
        # longer passes through it at all (above), and script_location is
        # "%"-escaped ("%%" is ConfigParser's literal-percent escape) since it
        # still goes through set_main_option.
        config = Config()
        config.set_main_option(
            "script_location", str(self._migrations_dir).replace("%", "%%")
        )
        self._backup_before_migration(config)
        with self._engine.connect() as connection:
            config.attributes["connection"] = connection
            command.upgrade(config, "head")
            connection.commit()

    def _backup_before_migration(self, config: Config) -> None:
        # Skipped entirely for ":memory:" (no file exists to back up) and for
        # a not-yet-existing database file (first run: nothing to protect).
        if self._db_path == ":memory:" or not os.path.exists(self._db_path):
            return

        script = ScriptDirectory.from_config(config)
        head = script.get_current_head()
        with self._engine.connect() as connection:
            current = MigrationContext.configure(connection).get_current_revision()

        if current == head:
            return

        self._write_backup()

    def _write_backup(self) -> None:
        # A plain `shutil.copy()` of the main database file alone is not
        # sufficient: SQLite (whatever this engine's journal mode — rollback
        # journal or WAL) can leave the main file, on its own, in a state
        # that is not an independently consistent snapshot while a journal/
        # WAL sidecar exists alongside it. `VACUUM INTO` asks SQLite itself
        # to produce a complete, self-consistent copy of the live database
        # (equivalent to a hot backup), correct regardless of journal mode,
        # without requiring this adapter to special-case WAL checkpointing
        # or `-wal`/`-shm` sidecar copying itself.
        backups_dir = Path(self._db_path).resolve().parent / "backups"
        backups_dir.mkdir(parents=True, exist_ok=True)
        db_name = Path(self._db_path).name
        backup_path = backups_dir / f"{db_name}.{time.strftime('%Y%m%dT%H%M%S')}.bak"

        # VACUUM INTO cannot run inside a transaction; SQLAlchemy's default
        # "begin once" connection mode would otherwise wrap it in one.
        with self._engine.connect().execution_options(isolation_level="AUTOCOMMIT") as connection:
            connection.execute(text("VACUUM INTO :path"), {"path": str(backup_path)})

        logger.info("pre-migration backup written to %s", backup_path)

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

    def list_cycles(self) -> list[UUID]:
        # No stored column carries a record's creation time (it lives inside
        # the JSON payload), so "most recent activity" is approximated by
        # SQLite's own implicit rowid, which increases monotonically with
        # insertion order — avoiding a schema change or deserializing every
        # row just to sort cycles.
        with Session(self._engine) as session:
            rows = session.execute(
                text(
                    "SELECT cycle_id FROM interaction_records "
                    "GROUP BY cycle_id ORDER BY MAX(rowid) DESC"
                )
            )
            return [UUID(row[0]) for row in rows]
