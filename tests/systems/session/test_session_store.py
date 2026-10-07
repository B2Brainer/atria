import pytest

from atria.domain import (
    CycleStatus,
    EpistemicStatus,
    FinishReason,
    InformationItem,
    Origin,
    Purpose,
    Session,
)
from atria.infrastructure.database import (
    PostgresInformationSystem,
    PostgresSessionStore,
    engine_from_url,
)
from atria.systems.information import InMemoryInformationSystem
from atria.systems.session import InMemorySessionStore, SessionError, SessionStore
from tests.systems.information.test_information_system import add, evaluation

PURPOSE = Purpose(text="Entender el ciclo de Atria")
OTHER = Purpose(text="Otro propósito")
FINISHED = {"status": CycleStatus.FINISHED, "finish_reason": FinishReason.ERROR}
ITEM = InformationItem(
    id="i1",
    content="contenido",
    status=EpistemicStatus.UNVERIFIED,
    origin=Origin.AI,
    iteration=1,
)


@pytest.fixture(params=["memory", pytest.param("postgres", marks=pytest.mark.db)])
def stores(request):
    """(sistema de información, almacén de sesiones, releer con conexión nueva)."""
    if request.param == "postgres":
        engine = request.getfixturevalue("pg_engine")
        url = engine.url.render_as_string(hide_password=False)

        def reread(session_id):
            fresh = engine_from_url(url)
            try:
                return PostgresSessionStore(fresh).get(session_id)
            finally:
                fresh.dispose()

        return PostgresInformationSystem(engine), PostgresSessionStore(engine), reread
    information = InMemoryInformationSystem()
    store = InMemorySessionStore(information)
    return information, store, store.get


def test_implementations_implement_interface(stores):
    assert isinstance(stores[1], SessionStore)


def test_created_session_has_default_lifecycle(stores):
    information, store, _ = stores
    state = information.create("s1", PURPOSE)

    assert store.get("s1") == Session(id="s1", purpose=PURPOSE, state=state)


def test_save_round_trip_updates_only_lifecycle(stores):
    information, store, reread = stores
    information.create("s1", PURPOSE)
    store.save(store.get("s1").model_copy(update={"max_iterations": 3}))

    store.save(store.get("s1").model_copy(update=FINISHED))

    stored = reread("s1")
    assert (stored.status, stored.finish_reason) == (
        CycleStatus.FINISHED,
        FinishReason.ERROR,
    )
    assert (stored.id, stored.purpose, stored.max_iterations) == ("s1", PURPOSE, 3)


def test_get_returns_current_state(stores):
    information, store, _ = stores
    information.create("s1", PURPOSE)
    store.save(store.get("s1"))
    information.apply("s1", evaluation(add("i1")))

    assert store.get("s1").state == information.get_state("s1")


@pytest.mark.parametrize(
    "mismatch",
    [
        lambda s: {
            "purpose": OTHER,
            "state": s.state.model_copy(update={"purpose": OTHER}),
        },
        lambda s: {"state": s.state.model_copy(update={"items": [ITEM]})},
        lambda s: {"id": "nadie"},
    ],
    ids=["other-purpose", "other-state", "unknown-session"],
)
def test_save_rejects_what_it_cannot_store(stores, mismatch):
    information, store, _ = stores
    information.create("s1", PURPOSE)
    session = store.get("s1")

    with pytest.raises(SessionError):
        store.save(session.model_copy(update={**mismatch(session), **FINISHED}))
    assert store.get("s1") == session


def test_unknown_session_is_an_error(stores):
    with pytest.raises(SessionError):
        stores[1].get("nadie")


def test_get_returns_a_copy(stores):
    information, store, _ = stores
    information.create("s1", PURPOSE)
    store.save(store.get("s1"))

    store.get("s1").state.items.append(ITEM)

    assert store.get("s1").state.items == []
