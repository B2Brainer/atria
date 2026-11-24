"""Acceptance criterion 9: core/ never imports adapters/, api/, httpx, or sqlalchemy."""

import ast
from pathlib import Path

CORE_ROOT = Path(__file__).resolve().parent.parent / "core"
FORBIDDEN_MODULES = ("adapters", "api", "httpx", "sqlalchemy")


def _imported_top_level_modules(source: str) -> set[str]:
    tree = ast.parse(source)
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                modules.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            modules.add(node.module.split(".")[0])
    return modules


def _core_python_files() -> list[Path]:
    return sorted(CORE_ROOT.rglob("*.py"))


def test_core_has_python_files_to_check():
    assert _core_python_files(), "expected core/ to contain Python modules"


def test_core_never_imports_forbidden_modules():
    violations = []
    for path in _core_python_files():
        modules = _imported_top_level_modules(path.read_text())
        hit = modules & set(FORBIDDEN_MODULES)
        if hit:
            violations.append((path, hit))

    assert not violations, f"forbidden imports found in core/: {violations}"
