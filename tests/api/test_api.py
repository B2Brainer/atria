import threading

import pytest
from fastapi.testclient import TestClient

from atria.api.app import create_app
from atria.infrastructure.ai_providers.fake import FakeProvider
from atria.infrastructure.database import (
    PostgresInformationSystem,
    PostgresSessionStore,
    PostgresTraceRecorder,
)
from atria.systems.ai import AIProvider, AIProviderError
from atria.systems.information import InMemoryInformationSystem
from atria.systems.session import InMemorySessionStore
from atria.systems.trace import InMemoryTraceRecorder

MAX = 5
SECRET = "sk-secret-123"


def client(provider: AIProvider, backend: str = "memory", engine=None) -> TestClient:
    if backend == "postgres":
        information = PostgresInformationSystem(engine)
        trace = PostgresTraceRecorder(engine)
        sessions = PostgresSessionStore(engine)
    else:
        information = InMemoryInformationSystem()
        trace = InMemoryTraceRecorder()
        sessions = InMemorySessionStore(information)
    app = create_app(information, trace, sessions, provider, max_iterations=MAX)
    return TestClient(app, raise_server_exceptions=False)


def create(api: TestClient, **body) -> str:
    response = api.post("/sessions", json={"purpose": "Entender Atria", **body})
    assert response.status_code == 201
    return response.json()["session_id"]


@pytest.fixture(params=["memory", pytest.param("postgres", marks=pytest.mark.db)])
def backend(request):
    if request.param == "postgres":
        return "postgres", request.getfixturevalue("pg_engine")
    return "memory", None


@pytest.mark.parametrize(
    ("script", "reason", "iterations"),
    [
        (["A", "A"], "purpose_fulfilled", 2),
        (["uno", "dos", "tres", "cuatro", "cinco"], "max_iterations", MAX),
        (["uno", AIProviderError("caído")], "error", 1),
    ],
)
def test_full_flow(backend, script, reason, iterations):
    api = client(FakeProvider(script), *backend)
    session_id = create(api)
    assert api.get(f"/sessions/{session_id}").json()["status"] == "running"

    run = api.post(f"/sessions/{session_id}/run")
    traces = api.get(f"/sessions/{session_id}/trace")
    retrospective = api.get(f"/sessions/{session_id}/retrospective")
    session = api.get(f"/sessions/{session_id}").json()

    assert run.status_code == traces.status_code == retrospective.status_code == 200
    assert retrospective.json() == run.json()
    assert retrospective.json()["finish_reason"] == reason
    assert len(traces.json()) == retrospective.json()["iterations"] == iterations
    assert session["status"] == "finished"
    assert session["finish_reason"] == reason
    assert session["state"] == traces.json()[-1]["resulting_state"]


@pytest.mark.parametrize("value", [1, MAX, None])
def test_valid_max_iterations_is_accepted(value):
    api = client(FakeProvider([]))

    assert create(api, max_iterations=value)


def test_body_max_iterations_bounds_the_cycle():
    api = client(FakeProvider(["uno", "dos", "tres"]))
    session_id = create(api, max_iterations=2)

    retrospective = api.post(f"/sessions/{session_id}/run").json()

    assert retrospective["finish_reason"] == "max_iterations"
    assert retrospective["iterations"] == 2
    assert api.get(f"/sessions/{session_id}").json()["max_iterations"] == 2


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"purpose": ""},
        {"purpose": "   "},
        {"purpose": None},
        {"purpose": "ok", "max_iterations": 0},
        {"purpose": "ok", "max_iterations": -1},
        {"purpose": "ok", "max_iterations": MAX + 1},
        {"purpose": "ok", "max_iterations": 1.5},
        {"purpose": "ok", "max_iterations": "muchas"},
        {"purpose": "ok", "max_iterations": "3"},
        {"purpose": "ok", "max_iterations": True},
        {"purpose": 123},
    ],
)
def test_invalid_create_body_is_422(body):
    api = client(FakeProvider([]))

    assert api.post("/sessions", json=body).status_code == 422


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("get", "/sessions/nadie"),
        ("get", "/sessions/nadie/trace"),
        ("get", "/sessions/nadie/retrospective"),
        ("post", "/sessions/nadie/run"),
    ],
)
def test_unknown_session_is_404(method, path):
    api = client(FakeProvider([]))

    assert getattr(api, method)(path).status_code == 404


def test_retrospective_of_unfinished_session_is_409():
    api = client(FakeProvider([]))
    session_id = create(api)

    assert api.get(f"/sessions/{session_id}/retrospective").status_code == 409


def test_running_a_finished_session_again_is_409():
    provider = FakeProvider(["A", "A"])
    api = client(provider)
    session_id = create(api)
    api.post(f"/sessions/{session_id}/run")

    assert api.post(f"/sessions/{session_id}/run").status_code == 409
    assert len(provider.requests) == 2


class BrokenProvider(AIProvider):
    """Viola el contrato: lanza un error que no es `AIProviderError`."""

    def complete(self, request):
        raise RuntimeError(f"openai.APIConnectionError: bad key {SECRET}")


def test_internal_error_is_generic_500(caplog):
    api = client(BrokenProvider())
    session_id = create(api)

    response = api.post(f"/sessions/{session_id}/run")

    assert response.status_code == 500
    assert response.json() == {"detail": "error interno"}
    for leak in ("Traceback", "RuntimeError", "openai", SECRET):
        assert leak not in response.text
    # El detalle sí queda en el log del servidor.
    assert SECRET in caplog.text
    assert api.get(f"/sessions/{session_id}").json()["status"] == "running"


class FlakyProvider(AIProvider):
    """Falla con un error interno en la segunda llamada y después responde."""

    def __init__(self) -> None:
        self.calls = 0

    def complete(self, request):
        self.calls += 1
        if self.calls == 2:
            raise RuntimeError("fallo interno")
        return FakeProvider(["A"]).complete(request)


def test_session_resumes_after_an_internal_error(backend):
    api = client(FlakyProvider(), *backend)
    session_id = create(api)

    assert api.post(f"/sessions/{session_id}/run").status_code == 500
    assert len(api.get(f"/sessions/{session_id}/trace").json()) == 1

    retrospective = api.post(f"/sessions/{session_id}/run").json()

    traces = api.get(f"/sessions/{session_id}/trace").json()
    assert retrospective["finish_reason"] == "purpose_fulfilled"
    assert [t["iteration"] for t in traces] == [1, 2]
    assert traces[1]["previous_state"] == traces[0]["resulting_state"]


class BlockingProvider(AIProvider):
    def __init__(self) -> None:
        self.started = threading.Event()
        self.release = threading.Event()

    def complete(self, request):
        self.started.set()
        assert self.release.wait(5)
        return FakeProvider(["A"]).complete(request)


def test_concurrent_run_of_the_same_session_is_409():
    provider = BlockingProvider()
    api = client(provider)
    session_id = create(api)
    first = {}
    worker = threading.Thread(
        target=lambda: first.update(r=api.post(f"/sessions/{session_id}/run"))
    )
    worker.start()
    assert provider.started.wait(5)

    second = api.post(f"/sessions/{session_id}/run")
    provider.release.set()
    worker.join(5)

    assert second.status_code == 409
    assert first["r"].status_code == 200
    assert api.post(f"/sessions/{session_id}/run").status_code == 409


def test_openapi_docs_are_served():
    api = client(FakeProvider([]))

    assert api.get("/docs").status_code == 200
    assert api.get("/openapi.json").status_code == 200
