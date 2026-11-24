"""CredentialPort — the boundary between the application core and secure credential storage."""

from abc import ABC, abstractmethod


class CredentialPort(ABC):
    @abstractmethod
    def get(self, reference: str) -> str:
        raise NotImplementedError

    @abstractmethod
    def store(self, reference: str, secret: str) -> None:
        raise NotImplementedError

    @abstractmethod
    def delete(self, reference: str) -> None:
        raise NotImplementedError
