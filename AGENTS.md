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
- `api/` — entry points composing `core/` and `adapters/`.
- `desktop/` — TypeScript/Electron project (renderer scaffolding reserved
  for a later increment).

As of this increment, all of the above are empty, importable scaffolding —
no business logic exists yet. Do not anticipate functionality from a later
increment (see the current approved spec in `specs/`).

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
