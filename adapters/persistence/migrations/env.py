"""Alembic environment: always runs online, against the URL PersistenceAdapter sets.

No ``alembic.ini`` file is used — ``PersistenceAdapter`` builds an in-memory
``alembic.config.Config`` and sets ``sqlalchemy.url``/``script_location``
programmatically before invoking ``alembic.command.upgrade``.
"""

from __future__ import annotations

from alembic import context
from sqlalchemy import engine_from_config, pool

config = context.config
target_metadata = None


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()
    connectable.dispose()


run_migrations_online()
