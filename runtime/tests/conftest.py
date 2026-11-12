"""What the suites share: the test database, migrated once."""

import os
from collections.abc import AsyncIterator

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine

from runtime.config import load_settings
from runtime.platform.service.schema import migrate_database
from runtime.postgres import create_engine

needs_the_database = pytest.mark.skipif("DATABASE_URL" not in os.environ, reason="the test database")


@pytest.fixture(scope="session")
async def engine() -> AsyncIterator[AsyncEngine]:
    """The test database, migrated to this release once per worker (the migration takes a lock)."""
    if "DATABASE_URL" not in os.environ:
        pytest.skip("the test database")
    made = create_engine(load_settings(), pool_size=5)
    await migrate_database(made)
    yield made
    await made.dispose()
