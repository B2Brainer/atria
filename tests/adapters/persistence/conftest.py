import pytest
from adapters.persistence.adapter import PersistenceAdapter


@pytest.fixture
def db_path(tmp_path):
    return str(tmp_path / "atria.sqlite3")


@pytest.fixture
def adapter(db_path):
    return PersistenceAdapter(db_path)
