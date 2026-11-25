"""`api/config.py`'s default database path must not depend on the process's
current working directory — it determines whether conversation history is
findable across launches (Increment 5's relaunch-persistence requirement),
and a desktop app's cwd at launch is not guaranteed to be stable.
"""

import os

from api.config import db_path


def test_default_db_path_is_independent_of_cwd(tmp_path, monkeypatch):
    monkeypatch.delenv("ATRIA_DB_PATH", raising=False)

    monkeypatch.chdir(tmp_path)
    from_one_cwd = db_path()

    other_cwd = tmp_path / "elsewhere"
    other_cwd.mkdir()
    monkeypatch.chdir(other_cwd)
    from_another_cwd = db_path()

    assert from_one_cwd == from_another_cwd
    assert os.path.isabs(from_one_cwd)


def test_env_var_override_still_wins(tmp_path, monkeypatch):
    override = str(tmp_path / "custom.sqlite3")
    monkeypatch.setenv("ATRIA_DB_PATH", override)

    assert db_path() == override
