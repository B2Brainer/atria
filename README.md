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
En v0 no hay migraciones: si cambia el esquema, la base se recrea.

## API

```sh
export ATRIA_DATABASE_URL=postgresql+psycopg://atria:atria@localhost:5432/atria
uv run uvicorn atria.api.main:app               # documentación en /docs
```

El proveedor de IA es la CLI de Codex (`codex exec`): requiere `codex` instalado y
autenticado con `codex login` (versión verificada: `codex-cli 0.160.1`). Atria no
gestiona credenciales. `ATRIA_CODEX_BIN`, `ATRIA_AI_MODEL` y `ATRIA_AI_TIMEOUT` son
opcionales (ver `.env.example`). Codex corre en solo lectura, en un directorio
temporal vacío y con una lista de inclusión de variables de entorno (`PATH`, `HOME`,
`LANG`, `TZ`, `USER`, `SHELL`, `LC_*`, `CODEX_*`) — nunca el entorno completo del
host, para que ningún secreto fuera de esa lista llegue al proceso. Si expira el
timeout se mata el grupo de procesos completo, no solo el proceso hijo directo. Los
tests `integration` hacen una llamada real y se saltan si `codex` no está en el
`PATH`; `uv run pytest -m "not integration"` no necesita ni red ni `codex`.

Sin alguna variable obligatoria, el arranque falla con un mensaje que la nombra.
`ATRIA_MAX_ITERATIONS` (10 por defecto) es el máximo por sesión. Un ciclo en curso se
protege contra ejecuciones simultáneas solo dentro del proceso: usar un único worker.
