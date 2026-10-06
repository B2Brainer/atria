"""Interfaz del registro de trazas, independiente del almacenamiento (p1 §4).

Cada iteración del ciclo deja una `IterationTrace`. La numeración de cada sesión es
consecutiva desde 1, y una traza registrada ya no cambia.
"""

from abc import ABC, abstractmethod

from atria.domain import IterationTrace


class TraceError(Exception):
    """Registro de traza inválido. No modifica lo almacenado."""


class TraceRecorder(ABC):
    @abstractmethod
    def record(self, trace: IterationTrace) -> None:
        """Registra la traza de la siguiente iteración de su sesión.

        Si la traza no es válida lanza `ValidationError`, y si su `iteration` no es
        la siguiente de la sesión lanza `TraceError`. En ambos casos no se almacena.
        """

    @abstractmethod
    def list(self, session_id: str) -> list[IterationTrace]:
        """Devuelve copias de las trazas de la sesión, en orden de iteración."""
