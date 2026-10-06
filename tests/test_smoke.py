import importlib

import pytest

PACKAGES = [
    "atria",
    "atria.domain",
    "atria.systems.information",
    "atria.systems.reasoning",
    "atria.systems.ai",
    "atria.orchestration",
    "atria.infrastructure.database",
    "atria.infrastructure.ai_providers",
    "atria.api",
]


@pytest.mark.parametrize("name", PACKAGES)
def test_package_imports(name):
    importlib.import_module(name)
