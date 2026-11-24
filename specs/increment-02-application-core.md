# Increment 2 — Application Core

Status: Draft

Agentic workflow for this increment follows the established process: spec-creator (this document) → human approval → Claude Code implementation → test-engineer verification → code-reviewer independent review → Marshal complementary review per its configured discipline → human final approval and integration authorization (`commit` skill).

## Objective

Implement the established interaction and record data models, the `InteractionManagement` and `InteractionRecordManagement` application operations, and the three architectural port contracts (`AIProviderPort`, `PersistencePort`, `CredentialPort`), according to the approved Data, Interfaces, and Detailed Behavior specifications, so that the application core is testable in isolation, independent of any external provider, persistence, or credential infrastructure.

## Scope

**Included:**

- `core/interaction/`: the `InteractionManagement` component.
  - Public operation (per Interfaces): `initiate(request: InteractionRequest) -> InteractionRecord`.
  - Private operations (per Detailed Behavior, invoked only through `initiate()`, not part of the module's public contract): `prepare_clean_interaction()`, `select_provider()`, `assemble_record()`.
  - `InteractionManagement` depends on `AIProviderPort` and `CredentialPort` (ports, not adapters) and on `InteractionRecordManagement`, per the Interfaces component relationships.
- `core/records/`: the `InteractionRecordManagement` component.
  - Public operations (per Interfaces): `get(record_id: UUID) -> InteractionRecord`, `list_by_cycle(cycle_id: UUID) -> List[InteractionRecord]`.
  - Private operations (per Detailed Behavior): `assign_sequence()`, `register_interaction()`, `reconstruct_conversation()`.
  - `InteractionRecordManagement` depends on `PersistencePort` (port, not adapter), per the Interfaces component relationships.
- `core/ports/`: the three port contracts, defined as abstract interfaces with no concrete implementation:
  - `AIProviderPort`: `execute(request: InteractionRequest) -> InteractionResult`.
  - `PersistencePort`: `save(record: InteractionRecord) -> None`, `get(record_id: UUID) -> InteractionRecord`, `list_by_cycle(cycle_id: UUID) -> List[InteractionRecord]`.
  - `CredentialPort`: `get(reference: String) -> String`, `store(reference: String, secret: String) -> None`, `delete(reference: String) -> None`.
- Data models (Pydantic), with the associations/cardinalities established in the Data specification:
  - `AIUsageCycle` (`id`, `created_at`); contains 0..* `InteractionRecord` (association, not composition).
  - `InteractionRecord` (`id`, `cycle_id`, `sequence`, `request`, `result`, `created_at`); composes exactly 1 `InteractionRequest` and 0..1 `InteractionResult`.
  - `InteractionRequest` (`input`, `provider_id`, `model_id`, `parameters`).
  - `InteractionResult` (`output`, `status`, `metrics`); composes 0..1 `ExecutionMetrics`.
  - `ExecutionMetrics` (`input_tokens`, `output_tokens`, `duration`, `cost`).
  - `ProviderConfiguration` (`provider_id`, `endpoint`, `credential_reference`); referenced (not composed) by `InteractionRequest` via provider/model selection.
- Unit tests for all data models (construction, validation, cardinality/field constraints) and for both components' operations, exercised against test doubles (fakes/stubs) implementing `AIProviderPort`, `PersistencePort`, and `CredentialPort` defined within the test suite.

**Excluded:**

- Real adapter implementations (`adapters/providers/`, `adapters/persistence/`, `adapters/credentials/`) — Increments 3 and 4.
- Adapter-internal private operations shown in Detailed Behavior (`prepare_provider_request()`, `send_request()`, `normalize_response()`, `serialize_record()`, `deserialize_record()`, `read_keychain()`, `write_keychain()`, `remove_keychain()`) — these belong to the adapters, not the core, and are out of scope.
- `api/` and `desktop/` (Electron/React UI, IPC) — Increments 5 and later; this increment's components are invoked only through their public operations in tests, not through any live UI or process boundary.
- Packaging/distribution — Increment 6.
- Prototype-wide validation — Increment 7.
- Modifying `Brainer/teoria/` (authoritative doc).
- Introducing HTTPX or SQLAlchemy usage into `core/` — those libraries are established for later increments' adapters; `core/` has no dependency on them.

## Design References

- `AI usage system.md`: Interaction, AI usage cycle, Clean AI Model, Clean Interaction — the conceptual basis for `prepare_clean_interaction()` and the `AIUsageCycle`/`InteractionRecord` model.
- `data/code.md` (Data specification, Mermaid class diagram): `AIUsageCycle`, `InteractionRecord`, `InteractionRequest`, `InteractionResult`, `ExecutionMetrics`, `ProviderConfiguration`, and their fields and cardinalities (`AIUsageCycle "1" o-- "0..*" InteractionRecord`, `InteractionRecord "1" *-- "1" InteractionRequest`, `InteractionRecord "1" *-- "0..1" InteractionResult`, `InteractionResult "1" *-- "0..1" ExecutionMetrics`, `InteractionRequest ..> ProviderConfiguration : selects`).
- `interfaces/code.md` (Interfaces specification): `InteractionInterface`, `RecordInterface`, `AIProviderPort`, `PersistencePort`, `CredentialPort` signatures; `InteractionManagement ..|> InteractionInterface`; `InteractionRecordManagement ..|> RecordInterface`; `InteractionManagement ..> AIProviderPort`, `..> CredentialPort`, `..> InteractionRecordManagement`; `InteractionRecordManagement ..> PersistencePort`.
- `preliminar behavior/code.md` (Preliminary Behavior): the Interaction Management flow (Initiate Clean Interaction → Prepare AI Request → Invoke AI Provider → Receive AI Response) and the Interaction Record Management flow (Create → Complete → Store; Retrieve), establishing the order of operations this increment's private methods implement.
- `detailed behavior/code.md` (Detailed Behavior flowchart): the core-side operation chains `initiate() → prepare_clean_interaction() → select_provider()` and `assemble_record() → assign_sequence() → register_interaction()`, the public/private marking (`＋`/`－`), and the port boundaries (`select_provider()` → `CredentialPort`; `register_interaction()` → `PersistencePort`; `get()`/`list_by_cycle()` → `PersistencePort`; retrieval path → `reconstruct_conversation()`). Adapter-internal nodes in this diagram are out of scope (see Scope).
- `atria-t0.md` → Technologies: Libraries (Pydantic, established for data models); Architectural Pattern (Hexagonal Architecture — ports as the boundary between core and adapters).
- `atria-t0.md` §6 "Implementation Plan": Increment 2 definition and deliverable; Increment 1 (prior, approved) established the empty `core/interaction/`, `core/records/`, `core/ports/` packages this increment fills; Increments 3–4 are explicitly deferred (adapter implementations).
- `atria-t0.md` §7 "Verification and Engineering Integrity": Unit Testing as the primary applicable method for this increment.
- `specs/increment-01-project-foundation.md`: established Python environment (`uv`, Python 3.13, Pytest, Ruff) this increment's code and tests run within; confirms `core/` packages currently contain no business logic.

## Expected Behavior

1. **Data models.** `core/interaction/` and/or `core/records/` (per established component ownership) define Pydantic models for `AIUsageCycle`, `InteractionRecord`, `InteractionRequest`, `InteractionResult`, `ExecutionMetrics`, and `ProviderConfiguration`, with the fields and types listed in the Data specification. `InteractionRecord` composes exactly one `InteractionRequest` and at most one `InteractionResult` (absent until the interaction completes); `InteractionResult` composes at most one `ExecutionMetrics`. Model validation rejects construction with incorrect types or missing required fields, consistent with Pydantic's standard validation behavior.

2. **Ports (`core/ports/`).** `AIProviderPort`, `PersistencePort`, and `CredentialPort` are defined as abstract base classes (or an equivalent explicit Python interface mechanism) declaring only the method signatures established in the Interfaces specification, with no implementation. No concrete adapter exists in this increment; `core/ports/` has no import dependency on `adapters/`.

3. **`InteractionManagement.initiate(request)`** (public): given a valid `InteractionRequest` and injected `AIProviderPort` and `CredentialPort` dependencies (and a collaborating `InteractionRecordManagement` instance), executes the sequence: `prepare_clean_interaction()` (establishes a request free of residual state from prior interactions, per the Clean Interaction definition) → `select_provider()` (resolves the `ProviderConfiguration`/credential reference for the request's `provider_id`, retrieving the credential via `CredentialPort.get()`) → invocation of `AIProviderPort.execute()` with the prepared request → `assemble_record()` (combines the original request and the returned `InteractionResult` into an `InteractionRecord`, delegating sequence assignment and registration to `InteractionRecordManagement`). Returns the resulting `InteractionRecord`.

4. **`InteractionRecordManagement`** operations:
   - `assign_sequence()` (private): determines the next `sequence` value for a new `InteractionRecord` within its `AIUsageCycle`, consistent with records already registered for that cycle.
   - `register_interaction()` (private): persists the assembled `InteractionRecord` via `PersistencePort.save()`.
   - `get(record_id)` (public): retrieves a single `InteractionRecord` via `PersistencePort.get()`.
   - `list_by_cycle(cycle_id)` (public): retrieves all `InteractionRecord`s for a cycle via `PersistencePort.list_by_cycle()`, invoking `reconstruct_conversation()` (private) to return them ordered by `sequence`, reconstructing the cycle's conversation order.

5. **Public/private boundary.** `initiate()`, `get()`, and `list_by_cycle()` are the only operations each component exposes as its public contract (matching `InteractionInterface`/`RecordInterface`). `prepare_clean_interaction()`, `select_provider()`, `assemble_record()`, `assign_sequence()`, `register_interaction()`, and `reconstruct_conversation()` are internal and must not be part of the components' external (tested-as-contract) API beyond what is needed for unit-level testing of internal behavior.

6. **Independence from infrastructure.** `core/interaction/` and `core/records/` depend only on `core/ports/` abstractions and the data models — never on `adapters/`, `api/`, HTTPX, or SQLAlchemy. All test execution substitutes fakes/stubs for the three ports.

## Acceptance Criteria

1. `core/ports/` defines `AIProviderPort`, `PersistencePort`, and `CredentialPort` as abstract interfaces exposing exactly the methods and signatures in the Interfaces specification (§ Design References), each raising `NotImplementedError` or being otherwise unusable without a concrete subclass.
2. Pydantic models exist for `AIUsageCycle`, `InteractionRecord`, `InteractionRequest`, `InteractionResult`, `ExecutionMetrics`, and `ProviderConfiguration`, with fields matching the Data specification; constructing `InteractionRecord` without a `request` fails validation, and constructing it without a `result` succeeds (0..1 cardinality).
3. `InteractionManagement.initiate(request)` returns an `InteractionRecord` whose `request` equals the input request and whose `result` equals the value produced by the injected `AIProviderPort.execute()` fake, when exercised against fakes for `AIProviderPort`, `CredentialPort`, and a real or fake `InteractionRecordManagement`.
4. `InteractionManagement.initiate(request)` invokes the injected `CredentialPort.get()` with the credential reference associated with the request's `provider_id` before invoking `AIProviderPort.execute()`, verifiable via a test double recording call order.
5. `InteractionRecordManagement.register_interaction()` invokes `PersistencePort.save()` exactly once per call with the fully assembled `InteractionRecord`, verifiable via a fake `PersistencePort`.
6. `InteractionRecordManagement.get(record_id)` returns the record produced by a fake `PersistencePort.get()` for a given `record_id`.
7. `InteractionRecordManagement.list_by_cycle(cycle_id)` returns all records registered for a cycle, ordered by `sequence`, when the underlying fake `PersistencePort.list_by_cycle()` returns them unordered.
8. Sequence assignment via `assign_sequence()` produces a strictly increasing `sequence` value for successive records registered within the same `AIUsageCycle`, verifiable against a fake persistence store seeded with existing records for that cycle.
9. None of `core/interaction/`, `core/records/`, or `core/ports/` imports from `adapters/`, `api/`, `httpx`, or `sqlalchemy` (confirmed by static inspection/independent code review).
10. `initiate()`, `get()`, and `list_by_cycle()` are the only operations invoked directly by this increment's acceptance-level/black-box tests; internal operations (`prepare_clean_interaction()`, `select_provider()`, `assemble_record()`, `assign_sequence()`, `register_interaction()`, `reconstruct_conversation()`) are exercised only via the public entry points or via tests explicitly scoped as internal/unit-level, not presented as part of the module's external contract.
11. `uv run pytest -q` passes with zero failures against the full test suite for this increment's code, and `uv run ruff check .` reports zero errors.

## Verification

- **Unit Testing** (criteria 1, 2, 5, 6, 7, 8): Pytest tests for each data model's validation behavior and cardinality constraints, and for each port's abstractness; tests for `InteractionRecordManagement`'s operations against a fake `PersistencePort`.
- **Integration Testing** (criteria 3, 4): Pytest tests exercising `InteractionManagement.initiate()` end-to-end against fakes for all three ports together with a real `InteractionRecordManagement`, verifying the full `prepare → select_provider → execute → assemble_record → register` sequence and call ordering.
- **Static Analysis** (criterion 9, part of 11): Ruff run against `core/`, plus an import-boundary check (e.g., grep/AST-based static inspection) confirming no forbidden imports from `core/` into `adapters/`, `api/`, `httpx`, or `sqlalchemy`.
- **Code Review** (criteria 9, 10, independent, per `code-reviewer`): confirms the public/private operation boundary matches the Interfaces specification and that no adapter-side behavior (Detailed Behavior's adapter nodes) was implemented in `core/`.
- **Acceptance Testing** (criterion 11): clean-checkout run of `uv run pytest -q` and `uv run ruff check .`, per `AGENTS.md`'s established verification commands.

## Constraints

- No new dependencies beyond Pydantic (already established and declared in Increment 1's `pyproject.toml`). HTTPX and SQLAlchemy remain declared for later increments but must not be imported by any module in `core/`.
- The public/private operation distinction marked in the Detailed Behavior diagram (`＋` vs `－`) must be preserved; private operations are implementation details of `initiate()` / `assemble_record()` / `list_by_cycle()` and are not to be exposed as alternative public entry points.
- Port abstractions must not embed any provider-, database-, or keychain-specific detail; they are the sole boundary `core/` has toward infrastructure, per Hexagonal Architecture.
- This increment must not implement or anticipate adapter behavior (Increments 3–4), IPC/UI behavior (Increment 5), or packaging (Increment 6).
- Changes to this specification's acceptance criteria to accommodate an implementation shortfall are not permitted; deviations must be reported, not silently reconciled.

## Open Decisions (require human resolution before or during implementation)

1. **`InteractionResult.status` values are not enumerated anywhere in the authoritative documentation.** The Data specification declares `status: String` with no defined vocabulary (e.g., `"success"`, `"failure"`), and the Detailed Behavior diagram shows no explicit failure branch from `invoke`/`receive`/`execute()` back through the core (no error path is drawn on the core side; `AIProviderPort.execute()` is modeled as always returning an `InteractionResult`). Since no real adapter exists yet (Increment 3/4), this increment cannot observe a genuine provider or persistence failure, but it does need to decide, for its own fakes/tests, whether: (a) `AIProviderPort.execute()` is permitted to raise an exception that `initiate()` must propagate or translate, or (b) all failure is represented strictly as a `status` value on a still-returned `InteractionResult` with no exception path. This increment's test doubles will encode whichever convention is chosen, and that choice will constrain Increment 4's real adapter contract. Recommend human decision before implementation begins; absence of a decision will default to treating `AIProviderPort.execute()` as able to raise, with `InteractionManagement` not catching or translating adapter exceptions (letting them propagate), since no catch/translate behavior is specified anywhere in Interfaces or Detailed Behavior — but this is this agent's interpretation, not an established decision, and should be confirmed.
2. **Persistence failure behavior is likewise unspecified.** `PersistencePort.save()`/`get()`/`list_by_cycle()` are not shown with any error path in Detailed Behavior. The same question applies: should `InteractionRecordManagement` catch and translate persistence exceptions, or propagate them untranslated? Recommend confirming alongside Decision 1, since both bear on whether this increment introduces any exception-translation logic in the core (which would be new behavior not drawn in any diagram) versus leaving all port-level exceptions to propagate unchanged (the more conservative, minimal reading of the established behavior).
3. **Ownership of data model definitions between `core/interaction/` and `core/records/` is not fully explicit.** The Data specification groups `AIUsageCycle`/`InteractionRecord` under namespace "Conversation" and `InteractionRequest`/`InteractionResult`/`ExecutionMetrics` under "Interaction", while the Interfaces diagram assigns `InteractionRecord` retrieval to `InteractionRecordManagement` and request/result construction to `InteractionManagement`. This spec defers the exact module placement (e.g., a shared `core/models.py` vs. splitting models across `core/interaction/` and `core/records/`) to implementation, provided the import-boundary and component-responsibility constraints above are respected; this is treated as an implementation detail, not a design decision, unless the operator disagrees.

Resolving Open Decisions 1 and 2 before implementation is recommended but not strictly blocking, since the increment's own scope (testable core with no real adapter) does not require a final answer — only a consistent convention for this increment's fakes. Human confirmation is requested before implementation locks in the default interpretation stated above.
