# AGENTS.md

Environment, architecture boundaries, and verification commands for Atria.
This file is the durable, repo-tracked record (per
`specs/increment-01-project-foundation.md` §5 "Development Infrastructure");
it complements, and does not restate, this session's `CLAUDE.md`, the agent
definitions (`spec-creator`, `test-engineer`, `code-reviewer`), the
`commit`/`load-bitbucket-ssh-key` skills, or Marshal's configuration —
general development discipline, agent roles, and Git/PR workflow live there.

## Development Environment

- **Python:** 3.13, managed with `uv`. Dependencies in `pyproject.toml`,
  locked in `uv.lock`.
- **TypeScript:** under `desktop/`, Node.js 24 LTS, managed with `npm`.
  Dependencies in `desktop/package.json`, locked in
  `desktop/package-lock.json`.

## Architecture Constraints

Hexagonal architecture, established by Atria's authoritative design
(`Brainer/teoria/`, not tracked in this repository):

- `core/` — application core (`interaction/`, `records/`, `ports/`). No
  dependency on `adapters/` or external libraries beyond what the core ports
  define.
- `adapters/` — adapters implementing `core/ports/` contracts
  (`providers/`, `persistence/`, `credentials/`). May depend on `core/`,
  never the reverse.
  - `adapters/persistence/` (Increment 3): `PersistenceAdapter`, SQLite via
    SQLAlchemy, schema migrations via Alembic (`adapters/persistence/migrations/`,
    no `alembic.ini` — `PersistenceAdapter` builds an in-memory `Config` and
    runs `upgrade("head")` on construction).
  - `adapters/credentials/` (Increment 3): `CredentialAdapter`, macOS Keychain
    via `pyobjc-framework-Security` direct bindings (in-process, no
    subprocess). Targets the legacy file-based Keychain, not the Data
    Protection keychain (`kSecUseDataProtectionKeychain`): that flag requires
    a code-signed binary with a `keychain-access-groups` entitlement, which
    this prototype does not have until Increment 6 (packaging/code
    signing/notarization) — a verified, operator-approved deviation from this
    increment's originally-approved spec, recorded there. darwin-only
    (`sys_platform == 'darwin'` dependency marker); `tests/adapters/credentials/`
    skips at module level (`allow_module_level=True`) on any non-macOS runner,
    per this increment's acceptance criteria — `uv run pytest -q` must still
    show at least one non-skipped run against a real macOS Keychain as part of
    this increment's reported verification evidence (local macOS run or a
    macOS CI runner), not CI's `ubuntu-latest` alone.
  - `adapters/providers/` — reserved for Increment 4 (HTTPX-based AI provider
    adapter).
- `api/` — entry points composing `core/` and `adapters/`.
- `desktop/` — TypeScript/Electron project (renderer scaffolding reserved
  for a later increment).

Through Increment 2, `adapters/` and `api/` were empty, importable scaffolding.
Increment 3 fills in `adapters/persistence/` and `adapters/credentials/`; do
not anticipate functionality from a later increment (see the current approved
spec in `specs/`).

## Verification Commands

Run from the repository root unless noted.

| Check | Command |
|---|---|
| Python install (reproducible) | `uv sync --locked` |
| Python tests | `uv run pytest -q` |
| Python static analysis | `uv run ruff check .` |
| TypeScript install (reproducible) | `npm ci` (run inside `desktop/`) |
| TypeScript tests | `npm run test` (inside `desktop/`) |
| TypeScript static analysis | `npm run lint` (inside `desktop/`) |

These are the exact steps CI (`.github/workflows/ci.yml`) runs on every push
and pull request.
