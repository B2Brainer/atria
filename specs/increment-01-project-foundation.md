# Increment 1 — Project Foundation

Status: Approved (operator, 2026-11-24)

Agentic workflow for this increment follows the established process: spec-creator (this document) → human approval → Claude Code implementation → test-engineer verification → code-reviewer independent review → Marshal complementary review per its configured discipline → human final approval and integration authorization (`commit` skill).

## Objective

Establish the repository structure, Python and TypeScript development environments, dependency management, testing tools, continuous integration, and agent instructions, so that subsequent increments have a reproducible development environment with a functioning verification workflow.

This increment produces infrastructure only. It does not implement any application functionality (interaction models, records, ports, adapters, or API).

## Scope

**Included:**

- Repository directory structure matching the established Project Organization (`core/`, `adapters/`, `api/`), created as placeholder packages/modules sufficient to be importable and testable, without business logic.
- `desktop/` directory, authorized by this specification, holding the base TypeScript development environment (`package.json`, lockfile, Vite, Vitest, ESLint configuration). This increment does not scaffold the Electron main process, preload script, or React renderer — those are reserved for Increment 5; `desktop/` in this increment contains only the TypeScript tooling baseline needed to run and verify it.
- Python development environment: `uv`-managed project (`pyproject.toml`, lockfile), Python package layout for `core/`, `adapters/`, `api/`. Python version fixed at 3.13.
- TypeScript development environment under `desktop/`: `npm`-managed project (`package.json`, lockfile) with Vite, Vitest, and ESLint configured. Node.js version fixed at 24 LTS. React and electron-builder are established technologies for later increments (5 and 6 respectively) and are therefore not declared as dependencies in this increment; introducing them remains in scope for the increment that implements the renderer/packaging.
- Dependency management for both environments: declared dependencies limited to those already established (Pydantic, HTTPX, SQLAlchemy for Python; Vite, Vitest, ESLint, TypeScript for the TypeScript tooling) plus the minimal supporting packages strictly necessary for those established tools to operate (e.g., type definitions, official Vite/ESLint/Vitest plugins required for TypeScript support), each individually justified in this specification. Pinned via lockfiles.
- Consistent declaration of the fixed Python 3.13 and Node.js 24 LTS versions across local development configuration (`pyproject.toml` Python version constraint; `package.json` `engines` field) and CI (GitHub Actions setup steps/matrix), per Correction #2 below.
- Testing tools configured and runnable with no tests or a minimal placeholder test: Pytest for Python, Vitest for TypeScript (under `desktop/`).
- Static analysis tools configured and runnable: Ruff for Python, ESLint for TypeScript (under `desktop/`).
- Continuous Integration: a GitHub Actions workflow (`.github/workflows/`) that runs the Python and TypeScript test suites and static analysis on push/pull request, using `uv sync --locked` and `npm ci` for installation.
- Agent instructions (`AGENTS.md`) defining only the material not already covered by `CLAUDE.md`, the established agents (`spec-creator`, `test-engineer`, `code-reviewer`), the `commit` and `load-bitbucket-ssh-key` skills, and Marshal configuration — specifically, the exact local verification commands for this increment's environments and any increment-specific conventions not already established elsewhere. `AGENTS.md` must not duplicate or redefine responsibilities already assigned by those sources.
- `specs/` directory established as the location for approved increment specifications.

**Excluded:**

- Implementation of interaction/record models, operations, or ports (`core/`) — Increment 2.
- Implementation of persistence, credential, or provider adapters — Increments 3 and 4.
- Electron main process, IPC bridge, or React UI implementation — Increment 5.
- Packaging, signing, notarization, or release workflows — Increment 6.
- Any business logic, data model, or interface behavior defined in the Data, Interfaces, or Detailed Behavior specifications.

## Design References

- atria-t0.md §"Implementation" → Project Organization (directory tree: `core/{interaction,records,ports}`, `adapters/{providers,persistence,credentials}`, `api/`). `desktop/` is not yet named in the established Project Organization tree; it is authorized by this specification as the location for the TypeScript/Electron project (per atria-t0.md's Electron/React/Node.js technologies), scoped in this increment to the base TypeScript tooling only.
- atria-t0.md → Technologies: Programming Languages (Python, TypeScript); Development Tools (uv, npm, Vite, Pytest, Vitest, Ruff, ESLint, electron-builder); Frameworks (Electron, React); Libraries (Pydantic, HTTPX, SQLAlchemy).
- atria-t0.md → Architecture: Hexagonal Architecture, Adapter pattern (informs the directory separation to establish, not its implementation).
- atria-t0.md §5 "Development Infrastructure": required repository artifacts (`AGENTS.md`, `specs/`, Implementation Roadmap, Git, GitHub Actions).
- atria-t0.md §6 "Implementation Plan": Increment 1 definition and its deliverable; subsequent increments (2–7) define the directories' eventual content, bounding what this increment must only scaffold.
- atria-t0.md §7 "Verification and Engineering Integrity": Unit Testing, Integration Testing, Acceptance Testing, Static Analysis as the established verification approaches.
- atria-t0.md → Development: Practices (Code Review, Continuous Integration).

## Expected Behavior

1. **Repository structure:** The repository contains the directories `core/interaction/`, `core/records/`, `core/ports/`, `adapters/providers/`, `adapters/persistence/`, `adapters/credentials/`, and `api/`, matching the established Project Organization. Each Python package directory contains an `__init__.py` (or equivalent minimal placeholder) so it is importable; no functional code is added.

2. **Python environment:** A `pyproject.toml` at the repository root declares the project, a Python version constraint fixed at 3.13, and its established dependencies (Pydantic, HTTPX, SQLAlchemy) plus development dependencies (Pytest, Ruff). `uv` manages the environment and produces a lockfile (`uv.lock`). Running `uv sync --locked` reproducibly installs the declared environment exactly as locked, failing if the lockfile is out of date with `pyproject.toml`.

3. **TypeScript environment:** A `package.json` under `desktop/` declares the base TypeScript project, its development dependencies (Vite, Vitest, ESLint, TypeScript, and the minimal supporting packages strictly necessary for them to operate — e.g. `@types/node`, the official Vite/ESLint/Vitest integration plugins required for TypeScript support), and an `engines` field fixing Node.js to 24 LTS. React and electron-builder are not declared in this increment (reserved for Increments 5 and 6). Running `npm ci` reproducibly installs the declared environment from the committed lockfile (`package-lock.json`), failing if the lockfile is out of sync with `package.json`.

4. **Testing tools:** Pytest is configured (via `pyproject.toml` or `pytest.ini`) to discover tests under the Python packages. Vitest is configured (via `vite.config.ts` or `vitest.config.ts` under `desktop/`) to discover tests under the TypeScript project. A minimal placeholder test exists in each environment to prove the test runner executes successfully against the established structure.

5. **Static analysis:** Ruff is configured (via `pyproject.toml`) with rules applicable to the established Python structure and runs without errors against the placeholder code. ESLint is configured (via `desktop/eslint.config.*` or equivalent) with rules applicable to the TypeScript project and runs without errors against the placeholder code.

6. **Continuous Integration:** A GitHub Actions workflow under `.github/workflows/` triggers on push and pull request, pinning Python 3.13 and Node.js 24 LTS. It installs both environments reproducibly (`uv sync --locked`, `npm ci`) and executes, at minimum: Pytest, Ruff (static analysis), and Vitest, ESLint (static analysis). The workflow fails if any step fails.

7. **Agent instructions:** An `AGENTS.md` file at the repository root documents only what is not already established by `CLAUDE.md`, the `spec-creator`/`test-engineer`/`code-reviewer` agent definitions, the `commit` and `load-bitbucket-ssh-key` skills, and Marshal's configuration: the exact local verification commands for this increment (Pytest, Ruff, Vitest, ESLint, with their working directories) and any increment-specific convention needed to operate the environments scaffolded here. It must not restate agent responsibilities, review workflow, or Git/PR discipline already defined by those sources.

8. **Specs directory:** A `specs/` directory exists at the repository root for approved increment specifications, consistent with §5.

## Acceptance Criteria

1. The repository root contains `core/interaction/`, `core/records/`, `core/ports/`, `adapters/providers/`, `adapters/persistence/`, `adapters/credentials/`, `api/`, and `desktop/`, matching the established Project Organization plus the `desktop/` authorization granted by this specification.
2. `uv sync --locked` completes successfully from a clean checkout and produces a working Python 3.13 environment with the established dependencies installed and `uv.lock` committed and in sync with `pyproject.toml`.
3. `npm ci` completes successfully from a clean checkout of `desktop/` and produces a working Node.js 24 LTS / TypeScript / Vite environment with the declared dependencies installed and `package-lock.json` committed and in sync with `package.json`.
4. Running the project's Pytest command executes successfully (zero failures) against the placeholder test(s).
5. Running the project's Vitest command executes successfully (zero failures) against the placeholder test(s) under `desktop/`.
6. Running Ruff against the repository reports zero errors (static analysis).
7. Running ESLint against the TypeScript project under `desktop/` reports zero errors (static analysis).
8. A GitHub Actions workflow file exists under `.github/workflows/`, triggers on push and pull request, pins Python 3.13 and Node.js 24 LTS, and executes criteria 2–7 (installation via `uv sync --locked`/`npm ci`, Pytest, Ruff, Vitest, ESLint); a workflow run on the increment's branch/PR completes with a passing status.
9. `AGENTS.md` exists at the repository root and documents only the verification commands and increment-specific conventions not already covered by `CLAUDE.md`, the established agents, the `commit`/`load-bitbucket-ssh-key` skills, and Marshal configuration, without duplicating their content.
10. `specs/` exists at the repository root.
11. No file under `core/`, `adapters/`, or `api/` contains business logic, data models, or interface behavior (i.e., contents are limited to package scaffolding and, at most, placeholder/test code), confirmed by independent code review (not static analysis alone).
12. No dependency is declared beyond those established in atria-t0.md or the minimal supporting packages justified in this specification (Design References / Scope); each supporting dependency present in `pyproject.toml` or `desktop/package.json` is traceable to a justification recorded in this specification.

## Verification

- **Static Analysis:** Ruff (Python) and ESLint (TypeScript) mechanical runs, verifying acceptance criteria 6 and 7. This is a distinct, automated check and does not by itself establish absence of business logic or architectural compliance.
- **Unit Testing:** Pytest and Vitest placeholder test execution, verifying acceptance criteria 4 and 5.
- **Integration Testing:** Not applicable — this increment introduces no component interactions to verify beyond environment setup, which is covered by the CI workflow execution (criterion 8).
- **Acceptance Testing:** A clean-checkout reproduction of `uv sync --locked` and `npm ci` (criteria 2 and 3), directory-structure inspection (criterion 1), and presence/content review of `AGENTS.md` and `specs/` (criteria 9 and 10), performed manually or via the CI workflow.
- **Code Review (independent, per `code-reviewer`):** Human-equivalent/independent-agent review confirming the absence of business logic, data models, or interface behavior in `core/`, `adapters/`, `api/` (criterion 11), and confirming that only justified dependencies were introduced (criterion 12). This is distinct from static analysis and is not satisfied by Ruff/ESLint passing.

## Constraints

- Dependencies are limited to those already established in atria-t0.md (Pydantic, HTTPX, SQLAlchemy, Vite, Vitest, ESLint, Pytest, Ruff, uv, npm, TypeScript) plus the minimal supporting packages justified in this specification's Scope/Expected Behavior sections as strictly necessary for those tools to operate. React and electron-builder remain established technologies but are out of scope for this increment's dependency declarations. Introducing any additional, unjustified dependency requires human approval as a new project requirement.
- The directory structure must match the established Project Organization, extended by the `desktop/` directory this specification authorizes; no other additional top-level directories or renaming is permitted without human approval.
- This increment must not anticipate or implement functionality reserved for Increments 2–6 (core models, adapters, IPC, UI, packaging) — including Electron main/preload/renderer scaffolding under `desktop/`, reserved for Increment 5. Scaffolding must remain structurally minimal (empty packages, configuration files, and placeholder tests only).
- Installation and reproducibility commands (local and CI) must use `uv sync --locked` and `npm ci`, not `uv sync` or `npm install`, to fail on lockfile drift rather than silently updating it.
- Python version is fixed at 3.13 and Node.js at 24 LTS, declared consistently in `pyproject.toml`/`package.json` ("engines") and in CI configuration.
- Changes to `AGENTS.md` content affecting agent responsibilities or architecture constraints are subject to the same human-approval requirement as specifications (§3, §4). `AGENTS.md` must complement, not duplicate, `CLAUDE.md`, the established agents, and the `commit`/`load-bitbucket-ssh-key` skills.
- **CI platform — resolved: GitHub Actions.** atria-t0.md establishes Git and GitHub Actions as Operational infrastructure (§"Infrastructure"/§5). The operator has since created the project's remote repository on GitHub (`git@github.com:B2Brainer/atria.git`), published `main` to it, and configured `.marshal/config.yaml` with `gate.default_destination: main`, making GitHub the actual, operative remote for this engagement. This resolves the earlier discrepancy noted against the engagement brief's Bitbucket reference: the CI workflow for this increment is GitHub Actions (`.github/workflows/`), consistent with both atria-t0.md and the operative remote. This decision was made and executed by the operator (repository creation and initial push), not inferred or decided by the agent. The brief's reference to Bitbucket and the `load-bitbucket-ssh-key` skill is accordingly obsolete with respect to the remote platform; correcting that reference is out of scope for this specification.
