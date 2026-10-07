"""Guardas de arquitectura: fronteras de importación de p1 §2 y §6 (ATR-012).

Recorre `atria/**/*.py` con `ast` y falla si un paquete importa algo que su fila de
`RULES` prohíbe. El composition root vive en `atria/api/` (p. ej. `api/main.py`),
que puede importar infraestructura; las filas globales le siguen aplicando.
"""

import ast
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]

AI_SDKS = ("openai", "anthropic", "google.genai", "mistralai")
ORM = ("sqlalchemy", "sqlmodel")

# (paquete al que aplica, subpaquete exento, módulos prohibidos). Una regla = una fila.
# Las filas de capa omiten SDKs de IA y ORM: las dos filas globales ya los cubren.
RULES = [
    (
        "atria.domain",
        None,
        (
            "atria.systems",
            "atria.orchestration",
            "atria.infrastructure",
            "atria.api",
            "fastapi",
        ),
    ),
    ("atria.systems", None, ("atria.infrastructure", "atria.api", "fastapi")),
    ("atria.orchestration", None, ("atria.infrastructure", "atria.api")),
    ("atria", "atria.infrastructure.ai_providers", AI_SDKS),
    ("atria", "atria.infrastructure.database", ORM),
]


def _within(module: str, prefix: str | None) -> bool:
    # Frontera por punto: `openai_utils` no está dentro de `openai`.
    return prefix is not None and (module == prefix or module.startswith(prefix + "."))


def imported_modules(tree: ast.Module, package: str):
    """(línea, módulo) por cada import; `package` resuelve los relativos."""
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                yield node.lineno, alias.name
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                parts = package.split(".")
                base = ".".join(parts[: len(parts) - node.level + 1])
                module = f"{base}.{node.module}" if node.module else base
            else:
                module = node.module
            yield node.lineno, module
            # `from atria import infrastructure` importa el subpaquete `atria.infrastructure`.
            for alias in node.names:
                yield node.lineno, f"{module}.{alias.name}"


def find_violations(root: Path) -> list[str]:
    violations = set()
    for path in sorted((root / "atria").rglob("*.py")):
        relative = path.relative_to(root)
        parts = relative.with_suffix("").parts
        is_package = parts[-1] == "__init__"
        module = ".".join(parts[:-1] if is_package else parts)
        package = module if is_package else module.rpartition(".")[0]
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for lineno, imported in imported_modules(tree, package):
            for applies_to, exempt, forbidden in RULES:
                if not _within(module, applies_to) or _within(module, exempt):
                    continue
                for prefix in forbidden:
                    if _within(imported, prefix):
                        scope = f"{applies_to} salvo {exempt}" if exempt else applies_to
                        violations.add(
                            f"{relative.as_posix()}:{lineno}: {prefix} prohibido en {scope}"
                        )
    return sorted(violations)


def _write(root: Path, relative: str, source: str) -> None:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(source, encoding="utf-8")


def test_current_code_respects_boundaries():
    # Sin esta comprobación, una ruta errónea daría un verde vacío.
    assert (REPO_ROOT / "atria" / "domain" / "__init__.py").is_file()
    assert find_violations(REPO_ROOT) == []


def test_violation_reports_file_and_line(tmp_path):
    _write(tmp_path, "atria/domain/bad.py", '"""Módulo temporal."""\n\nimport openai\n')

    assert find_violations(tmp_path) == [
        "atria/domain/bad.py:3: openai prohibido en atria salvo atria.infrastructure.ai_providers"
    ]


@pytest.mark.parametrize(
    ("relative", "source"),
    [
        ("atria/domain/m.py", "import openai"),
        ("atria/domain/m.py", "import openai.types"),
        ("atria/systems/m.py", "from openai import OpenAI"),
        ("atria/api/m.py", "import anthropic"),
        ("atria/infrastructure/database/m.py", "import openai"),
        ("atria/orchestration/m.py", "from sqlalchemy.orm import Session"),
        ("atria/infrastructure/ai_providers/m.py", "import sqlmodel"),
        ("atria/domain/m.py", "import fastapi"),
        ("atria/domain/m.py", "from atria.systems.ai import AISystem"),
        ("atria/domain/m.py", "from atria.infrastructure.database import tables"),
        ("atria/systems/m.py", "from ..infrastructure import database"),
        ("atria/systems/ai/m.py", "from ...infrastructure.database import tables"),
        ("atria/domain/m.py", "from .. import api"),
        ("atria/domain/__init__.py", "from ..orchestration import Orchestrator"),
        ("atria/systems/ai/__init__.py", "from ... import infrastructure"),
        ("atria/orchestration/m.py", "from atria import infrastructure"),
        ("atria/orchestration/m.py", "def f():\n    import atria.api.app\n"),
    ],
)
def test_detects_import_forms(tmp_path, relative, source):
    _write(tmp_path, relative, source + "\n")

    assert [v.split(":")[0] for v in find_violations(tmp_path)] == [relative]


@pytest.mark.parametrize(
    ("relative", "source"),
    [
        ("atria/infrastructure/ai_providers/m.py", "import openai"),
        ("atria/infrastructure/database/m.py", "from sqlalchemy import Engine"),
        (
            "atria/api/main.py",
            "from atria.infrastructure.database import engine_from_url",
        ),
        ("atria/api/app.py", "from fastapi import FastAPI"),
        ("atria/orchestration/m.py", "from atria.systems.ai import AISystem"),
        ("atria/systems/ai/m.py", "from ..information import InformationSystem"),
        ("atria/domain/m.py", "from . import ai"),
        ("atria/domain/__init__.py", "from .ai import AIRequest"),
        ("atria/domain/m.py", "import openai_utils"),
    ],
)
def test_allows_legitimate_imports(tmp_path, relative, source):
    _write(tmp_path, relative, source + "\n")

    assert find_violations(tmp_path) == []


@pytest.mark.parametrize(
    ("relative", "source"),
    [
        ("atria/infrastructure/ai_providers_extra.py", "import openai"),
        ("atria/infrastructure/database_extra.py", "import sqlalchemy"),
    ],
)
def test_exemption_does_not_leak_to_sibling_prefix(tmp_path, relative, source):
    _write(tmp_path, relative, source + "\n")

    assert [v.split(":")[0] for v in find_violations(tmp_path)] == [relative]
