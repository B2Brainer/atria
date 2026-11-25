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

## Distribution and Operations (Increment 6)

- **Packaging:** `npm run package:mac` (inside `desktop/`) builds the
  renderer/main/preload bundles, provisions a standalone `uv`-managed Python
  runtime with the project's locked dependencies installed directly into it
  (`desktop/scripts/build-python-dist.sh` — no PyInstaller or other freezing
  tool), and runs `electron-builder` to produce a `.dmg`/`.zip` under
  `desktop/dist/`. The packaged application does not require Python, `uv`, or
  Node.js to be separately installed on the target machine.
- **Signing/notarization:** macOS code signing and notarization run
  automatically when `CSC_LINK`/`CSC_KEY_PASSWORD` (signing) and
  `APPLE_ID`/`APPLE_APP_SPECIFIC_PASSWORD`/`APPLE_TEAM_ID` (notarization) are
  present as environment variables / GitHub Actions secrets; their absence
  does not fail the build — it produces an unsigned, clearly labeled
  development artifact instead (see `desktop/electron-builder.yml`,
  `desktop/scripts/notarize.cjs`).
- **Release process:** pushing a `v*` tag triggers
  `.github/workflows/release.yml` (independent of `ci.yml`'s own push/PR
  triggers), which packages the macOS artifact and publishes it to GitHub
  Releases — as a draft, labeled `-unsigned`, when no signing secrets are
  configured. Obtaining a new version is always a manual download-and-install
  from that GitHub Release; the application has no auto-update mechanism.
- **Local structured logging:** both the Python backend
  (`logs/atria-backend.log`, overridable via `ATRIA_LOG_PATH`;
  `api/logging_config.py`) and the Electron main process
  (`app.getPath("logs")/atria-main.log`, overridable via `ATRIA_LOG_PATH`;
  `desktop/src/main/logger.ts`) write JSON-lines log records, rotated at 5 MB
  per file with at most 3 rotated files retained. No log record ever contains
  a secret, resolved credential, provider authentication header, or raw
  interaction content.
- **Backup and recovery:** before applying a pending Alembic migration,
  `PersistenceAdapter` writes a consistent backup of the current database to
  a `backups/` directory alongside it, via SQLite's `VACUUM INTO` (correct
  regardless of journal mode — not a plain file copy, which can be
  inconsistent under WAL or a pending rollback journal). **Manual restore
  procedure:** stop the application, replace the live database file (default
  `atria.sqlite3`, or `ATRIA_DB_PATH`) with the chosen file from its
  `backups/` subdirectory, then restart the application.
