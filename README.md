# Atria

Requisitos: Python >= 3.12 y [uv](https://docs.astral.sh/uv/).

```sh
uv sync --frozen        # instala el entorno desde uv.lock
uv run pytest           # corre los tests
uv run ruff check .     # corre el linter
```

## Base de datos (PostgreSQL)

Los tests marcados `db` necesitan un PostgreSQL. En local, con Docker:

```sh
docker run -d --name atria-pg -p 5432:5432 \
  -e POSTGRES_USER=atria -e POSTGRES_PASSWORD=atria -e POSTGRES_DB=atria_test \
  postgres:17
export ATRIA_TEST_DATABASE_URL=postgresql+psycopg://atria:atria@localhost:5432/atria_test
uv run pytest -m db     # solo los tests de PostgreSQL
```

`ATRIA_TEST_DATABASE_URL` es solo para tests: cada test vacía las tablas de esa base.
Sin ella, los tests `db` se saltan (`uv run pytest -rs` lo muestra). La aplicación usa
`ATRIA_DATABASE_URL` (ver `.env.example`); las tablas se crean con `create_schema`.
