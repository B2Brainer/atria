import pytest

from atria.domain import (
    ActionType,
    AIRequest,
    AIResult,
    Decision,
    InformationState,
    Purpose,
)
from atria.infrastructure.ai_providers.fake import FakeProvider
from atria.systems.ai import AIProvider, AIProviderError, AISystem, AITimeoutError

PURPOSE = Purpose(text="Entender el ciclo de Atria")
STATE = InformationState(purpose=PURPOSE)


def decision(instruction: str = "Explica el ciclo") -> Decision:
    return Decision(action=ActionType.EXPLORE, instruction=instruction)


def run(provider: FakeProvider, *instructions: str) -> list[str]:
    """Ejecuta una instrucción por llamada y devuelve cada salida o el error."""
    system = AISystem(provider)
    outputs = []
    for instruction in instructions:
        try:
            outputs.append(system.execute(decision(instruction), STATE).content)
        except AIProviderError as error:
            outputs.append(f"{type(error).__name__}: {error}")
    return outputs


def test_fake_implements_provider_port():
    assert isinstance(FakeProvider([]), AIProvider)


def test_execute_returns_scripted_response():
    result = AISystem(FakeProvider(["respuesta"])).execute(decision(), STATE)

    assert result == AIResult(content="respuesta")


def test_request_carries_purpose_and_decision_instruction():
    provider = FakeProvider(["respuesta"])

    AISystem(provider).execute(decision("Resume el estado"), STATE)

    assert provider.requests == [
        AIRequest(purpose=PURPOSE, instruction="Resume el estado")
    ]


def test_script_is_consumed_in_order_and_every_request_recorded():
    provider = FakeProvider(["r1", "r2"])

    assert run(provider, "i1", "i2") == ["r1", "r2"]
    assert [request.instruction for request in provider.requests] == ["i1", "i2"]


@pytest.mark.parametrize("error_type", [AIProviderError, AITimeoutError])
def test_provider_error_propagates_as_domain_error(error_type):
    provider = FakeProvider([error_type("fallo"), "después"])
    system = AISystem(provider)

    with pytest.raises(error_type, match="fallo"):
        system.execute(decision("i1"), STATE)

    assert [request.instruction for request in provider.requests] == ["i1"]
    assert system.execute(decision("i2"), STATE).content == "después"


def test_same_inputs_produce_same_outputs():
    def script():
        return ["r1", AITimeoutError("lento"), "r3"]

    instructions = ("i1", "i2", "i3", "i4")

    first = run(FakeProvider(script()), *instructions)
    second = run(FakeProvider(script()), *instructions)

    assert first == second
    assert first[:3] == ["r1", "AITimeoutError: lento", "r3"]


def test_exhausted_script_raises_provider_error():
    provider = FakeProvider(["r1"])
    system = AISystem(provider)
    system.execute(decision(), STATE)

    with pytest.raises(AIProviderError):
        system.execute(decision(), STATE)


def test_mutating_script_after_construction_does_not_change_responses():
    script = ["r1"]
    provider = FakeProvider(script)
    script[0] = "otra"
    script.append("r2")

    assert run(provider, "i1", "i2")[0] == "r1"
    assert run(provider, "i3")[0].startswith("AIProviderError")


def test_recorded_request_does_not_alias_state():
    state = InformationState(purpose=Purpose(text="Original"))
    provider = FakeProvider(["r1"])

    AISystem(provider).execute(decision(), state)
    state.purpose.text = "Mutado"

    assert provider.requests[0].purpose == Purpose(text="Original")
