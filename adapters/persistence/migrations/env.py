"""Alembic environment: runs online, against the connection PersistenceAdapter passes.

No ``alembic.ini`` file is used — ``PersistenceAdapter`` builds an in-memory
``alembic.config.Config`` and passes its own live SQLAlchemy connection via
``config.attributes["connection"]`` (never a ``sqlalchemy.url`` string), so
migrations always run against the exact same connection/engine the adapter
uses for ``save``/``get``/``list_by_cycle`` — correct even for a `:memory:`
database, where a second engine built from a URL string would open its own,
unrelated in-memory database.
"""

from __future__ import annotations

from alembic import context

config = context.config
target_metadata = None


def run_migrations_online() -> None:
    connection = config.attributes["connection"]
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


run_migrations_online()
