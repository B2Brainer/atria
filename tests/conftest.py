import os

import pytest
from sqlalchemy import text

from atria.infrastructure.database import create_schema, engine_from_url
from atria.infrastructure.database.tables import metadata

TEST_URL_VARIABLE = "ATRIA_TEST_DATABASE_URL"


@pytest.fixture(scope="session")
def _pg_engine_once():
    # Variable propia de los tests: cada test vacía las tablas de esa base.
    raw = os.environ.get(TEST_URL_VARIABLE, "")
    if not raw.strip():
        pytest.skip(f"{TEST_URL_VARIABLE} no está definida (ver README)")
    engine = engine_from_url(raw, TEST_URL_VARIABLE)
    # Base desechable: se recrea porque `create_all` no altera tablas existentes.
    metadata.drop_all(engine)
    create_schema(engine)
    yield engine
    engine.dispose()


@pytest.fixture
def pg_engine(_pg_engine_once):
    with _pg_engine_once.begin() as conn:
        conn.execute(text("TRUNCATE session, information_item, iteration"))
    return _pg_engine_once
