"""Adaptador del proveedor de IA: la CLI de Codex (`codex exec`) como proceso local (p1 §5).

Configuración desde el entorno (ver `.env.example`): `ATRIA_CODEX_BIN` (`codex` por
defecto), `ATRIA_AI_MODEL` (opcional) y `ATRIA_AI_TIMEOUT` (segundos, 30 por defecto).
La autenticación es la de la propia CLI (`codex login`): Atria no maneja credenciales.

Codex se ejecuta sin escritura (`--sandbox read-only`), sin persistir sesión, en un
directorio vacío y temporal, y con una lista de inclusión de variables de entorno
(nunca el entorno completo del host: es un agente con capacidad de shell, y un
deny-list de solo `ATRIA_*` dejaría pasar cualquier otro secreto del host, p. ej.
`GITHUB_TOKEN` o credenciales de nube). Su stdout/stderr se descartan (pueden
contener rutas del host o datos de la cuenta); la respuesta se lee del archivo
de `--output-last-message`. Al expirar el timeout se mata el grupo de procesos
completo (`start_new_session=True` + `os.killpg`), no solo el proceso hijo
directo, para que un nieto que `codex exec` haya generado no quede huérfano.
Los errores salen como `AIProviderError` / `AITimeoutError` con mensajes
genéricos y sin encadenar la excepción original.
"""

import math
import os
import shutil
import signal
import subprocess
import tempfile
from pathlib import Path

from atria.domain import AIRequest, AIResult
from atria.systems.ai import AIProvider, AIProviderError, AITimeoutError

DEFAULT_TIMEOUT_SECONDS = 30.0

# Lista de inclusión: solo lo que `codex` necesita para resolverse y ejecutarse
# (el binario en PATH, el home del usuario para su propia configuración/sesión
# de `codex login`, locale/zona horaria) y su propio namespace de configuración
# (`CODEX_*`). Todo lo demás del entorno del host -incluyendo cualquier secreto
# no prefijado con ATRIA_- se excluye por defecto.
_ALLOWED_ENV_KEYS = frozenset({"PATH", "HOME", "LANG", "TZ", "USER", "SHELL"})
_ALLOWED_ENV_PREFIXES = ("LC_", "CODEX_")


def _filtered_subprocess_env() -> dict[str, str]:
    return {
        k: v
        for k, v in os.environ.items()
        if k in _ALLOWED_ENV_KEYS or k.startswith(_ALLOWED_ENV_PREFIXES)
    }


class AIConfigurationError(Exception):
    """Configuración del proveedor ausente o inválida. Nunca incluye su valor."""


def _timeout_from_env() -> float:
    raw = os.environ.get("ATRIA_AI_TIMEOUT", "").strip()
    if not raw:
        return DEFAULT_TIMEOUT_SECONDS
    try:
        timeout = float(raw)
    except ValueError:
        timeout = 0.0
    if not (math.isfinite(timeout) and timeout > 0):
        raise AIConfigurationError(
            "ATRIA_AI_TIMEOUT debe ser un número de segundos mayor que 0"
        )
    return timeout


class CodexCLIProvider(AIProvider):
    def __init__(self) -> None:
        binary = shutil.which(os.environ.get("ATRIA_CODEX_BIN", "").strip() or "codex")
        if binary is None:
            raise AIConfigurationError(
                "no se encuentra el binario de codex (PATH o ATRIA_CODEX_BIN)"
            )
        self._binary = binary
        self._model = os.environ.get("ATRIA_AI_MODEL", "").strip() or None
        self._timeout = _timeout_from_env()

    def complete(self, request: AIRequest) -> AIResult:
        prompt = f"Propósito: {request.purpose.text}\n\n{request.instruction}"
        env = _filtered_subprocess_env()
        with tempfile.TemporaryDirectory(prefix="atria-codex-") as tmp:
            workdir = Path(tmp) / "work"
            workdir.mkdir()
            output = Path(tmp) / "last-message.txt"
            args = [
                self._binary,
                "exec",
                "--sandbox",
                "read-only",
                "--skip-git-repo-check",
                "--ephemeral",
                "--cd",
                str(workdir),
                "--output-last-message",
                str(output),
                *(["--model", self._model] if self._model else []),
                "-",  # el prompt llega por stdin
            ]
            try:
                # `start_new_session=True` pone al hijo en su propio grupo de
                # procesos, para poder matar al grupo completo -no solo al hijo
                # directo- si `codex exec` genera nietos que sobrevivirían a un
                # `kill` del solo proceso hijo tras un timeout.
                process = subprocess.Popen(
                    args,
                    stdin=subprocess.PIPE,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    cwd=workdir,
                    env=env,
                    text=True,
                    encoding="utf-8",
                    start_new_session=True,
                )
            except OSError:
                raise AIProviderError(
                    "no se pudo ejecutar el proveedor de IA"
                ) from None
            try:
                process.communicate(input=prompt, timeout=self._timeout)
            except subprocess.TimeoutExpired:
                self._kill_process_group(process)
                raise AITimeoutError(
                    "el proveedor de IA no respondió a tiempo"
                ) from None
            if process.returncode != 0:
                raise AIProviderError(
                    f"el proveedor de IA terminó con código {process.returncode}"
                )
            try:
                content = output.read_text(encoding="utf-8").strip()
            except (OSError, UnicodeDecodeError):
                content = ""
        if not content:
            raise AIProviderError(
                "el proveedor de IA devolvió una respuesta sin contenido"
            )
        return AIResult(content=content)

    @staticmethod
    def _kill_process_group(process: subprocess.Popen) -> None:
        try:
            os.killpg(os.getpgid(process.pid), signal.SIGKILL)
        except ProcessLookupError:
            pass  # ya había terminado
        process.communicate()  # reap: evita un proceso zombie
