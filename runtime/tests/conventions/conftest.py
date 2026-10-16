"""The one fixture the convention tests share: the tree under src/, parsed once per session."""

import pytest

from tests.conventions.canon import Module, read_modules


@pytest.fixture(scope="session")
def modules() -> dict[str, Module]:
    """Every module of the package, by name."""
    return read_modules()
