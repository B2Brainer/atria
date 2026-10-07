import traceback

import pytest

from atria.domain import (
    ChangeKind,
    EpistemicStatus,
    Evaluation,
    InformationItem,
    Origin,
    Purpose,
    Session,
    StateChange,
    Verdict,
)
from atria.infrastructure.ai_providers.fake import FakeProvider
from atria.infrastructure.database import (
    DatabaseConfigurationError,
    PostgresInformationSystem,
    PostgresSessionStore,
    PostgresTraceRecorder,
    engine_from_env,
    engine_from_url,
)
from atria.orchestration import Orchestrator
from atria.systems.ai import AIProviderError, AISystem
from atria.systems.information import InMemoryInformationSystem
from atria.systems.reasoning import ReasoningSystem
from atria.systems.trace import InMemoryTraceRecorder

PURPOSE = Purpose(text="Entender el ciclo de Atria")


def fresh(pg_engine):
    """Un engine nuevo sobre la misma base: relee sin conexiones ni cachés previas."""
    return engine_from_url(pg_engine.url.render_as_string(hide_password=False))


def item(id: str) -> InformationItem:
    return InformationItem(
        id=id,
        content=f"contenido {id}",
        status=EpistemicStatus.UNVERIFIED,
        origin=Origin.AI,
        iteration=1,
    )


@pytest.mark.db
def test_information_round_trip_promotes_only_the_target(pg_engine):
    system = PostgresInformationSystem(pg_engine)
    system.create("s1", PURPOSE)
    system.apply(
        "s1",
        Evaluation(
            verdict=Verdict.ACCEPT,
            changes=[
                StateChange(kind=ChangeKind.ADD_INFORMATION, item=item("i1")),
                StateChange(kind=ChangeKind.ADD_INFORMATION, item=item("i2")),
            ],
        ),
    )

    system.apply(
        "s1",
        Evaluation(
            verdict=Verdict.ACCEPT,
            changes=[StateChange(kind=ChangeKind.PROMOTE, target_id="i1")],
        ),
    )

    engine = fresh(pg_engine)
    state = PostgresInformationSystem(engine).get_state("s1")
    engine.dispose()
    assert state.accepted == [item("i1").model_copy(update={"status": "accepted"})]
    assert state.unverified == [item("i2")]
    assert state.purpose == PURPOSE


@pytest.mark.db
def test_trace_round_trip_keeps_every_field(pg_engine):
    from tests.systems.trace.test_trace_recorder import trace

    traces = [trace(1), trace(2), trace(3)]
    recorder = PostgresTraceRecorder(pg_engine)
    for t in traces:
        recorder.record(t)

    engine = fresh(pg_engine)
    listed = PostgresTraceRecorder(engine).list("s1")
    engine.dispose()
    assert [t.model_dump() for t in listed] == [t.model_dump() for t in traces]


def run_cycle(information, trace, script):
    orchestrator = Orchestrator(
        information,
        ReasoningSystem(max_iterations=3, promote_on_repetition=True),
        AISystem(FakeProvider(script)),
        trace,
    )
    state = information.create("s1", PURPOSE)
    session, _ = orchestrator.run(Session(id="s1", purpose=PURPOSE, state=state))
    return session


@pytest.mark.db
@pytest.mark.parametrize(
    "script",
    [["A", "A"], ["uno", "dos", "tres"], ["uno", AIProviderError("caído")]],
    ids=["fulfilled", "max-iterations", "error"],
)
def test_cycle_on_postgres_matches_in_memory(pg_engine, script):
    memory_trace = InMemoryTraceRecorder()
    expected = run_cycle(InMemoryInformationSystem(), memory_trace, script)

    pg_trace = PostgresTraceRecorder(pg_engine)
    session = run_cycle(PostgresInformationSystem(pg_engine), pg_trace, script)
    PostgresSessionStore(pg_engine).save(session)

    engine = fresh(pg_engine)
    stored = PostgresSessionStore(engine).get("s1")
    traces = PostgresTraceRecorder(engine).list("s1")
    engine.dispose()
    assert session == expected
    assert stored == expected
    assert len(traces) == len(memory_trace.list("s1")) > 0
    assert traces[-1].resulting_state == stored.state


def test_missing_database_url_fails_with_clear_message(monkeypatch):
    monkeypatch.delenv("ATRIA_DATABASE_URL", raising=False)

    with pytest.raises(DatabaseConfigurationError, match="falta la variable"):
        engine_from_env()


@pytest.mark.parametrize(
    "url",
    [
        "postgresql+psycopg://atria:s3cr3t-pw@host:no-es-puerto/db",
        "sqlite:///s3cr3t-pw.db",
    ],
    ids=["unparseable", "not-postgres"],
)
def test_invalid_database_url_does_not_leak_it(monkeypatch, url):
    monkeypatch.setenv("ATRIA_DATABASE_URL", url)

    with pytest.raises(DatabaseConfigurationError) as raised:
        engine_from_env()

    # Incluye las excepciones encadenadas: es lo que acabaría en un log.
    assert "s3cr3t-pw" not in "".join(traceback.format_exception(raised.value))
