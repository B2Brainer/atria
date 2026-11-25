"""Acceptance criterion 1: core/ports/ defines the three ports as abstract interfaces."""

import pytest
from core.ports.credentials import CredentialPort
from core.ports.persistence import PersistencePort
from core.ports.provider import AIProviderPort


@pytest.mark.parametrize("port_cls", [AIProviderPort, PersistencePort, CredentialPort])
def test_port_cannot_be_instantiated_directly(port_cls):
    with pytest.raises(TypeError):
        port_cls()


def test_ai_provider_port_requires_execute():
    class Incomplete(AIProviderPort):
        pass

    with pytest.raises(TypeError):
        Incomplete()


def test_persistence_port_requires_all_methods():
    class Incomplete(PersistencePort):
        def save(self, record):
            return None

    with pytest.raises(TypeError):
        Incomplete()


def test_credential_port_requires_all_methods():
    class Incomplete(CredentialPort):
        def get(self, reference):
            return ""

    with pytest.raises(TypeError):
        Incomplete()


def test_ports_expose_established_methods():
    assert set(AIProviderPort.__abstractmethods__) == {"execute"}
    assert set(PersistencePort.__abstractmethods__) == {
        "save",
        "get",
        "list_by_cycle",
        "list_cycles",
    }
    assert set(CredentialPort.__abstractmethods__) == {"get", "store", "delete"}
