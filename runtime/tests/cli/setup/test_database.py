"""The box's own keys `setup` draws: the runner's a row the database must know, the fleets' drawn once."""

import os
from collections.abc import Iterator
from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from runtime.accounts.service import actor
from runtime.cli.setup import database
from runtime.cli.setup.env_file import EnvFile
from runtime.scoping import box_wide
from tests.conftest import needs_the_database

FORGOTTEN = "pc_of_a_database_deleted"


# `prepare_database` hands the machine's settings to the process (the revisions read them there):
# the suite's own environment is put back after each test.
@pytest.fixture
def environment() -> Iterator[None]:
    kept = dict(os.environ)
    yield
    os.environ.clear()
    os.environ.update(kept)


@needs_the_database
@pytest.mark.usefixtures("environment")
async def test_a_runner_key_the_database_does_not_know_is_drawn_again_and_kept_after(
    tmp_path: Path, engine: AsyncEngine, sessions: async_sessionmaker[AsyncSession]
) -> None:
    """`down --volumes` keeps the env file: its runner key is of a database that is gone, and setup draws another."""
    del engine
    env = EnvFile(tmp_path / "env")
    env.create(f"PINECALL_VAULT_KEY={os.environ['PINECALL_VAULT_KEY']}\n{database.RUNNER_KEY}={FORGOTTEN}\n")
    await database.prepare_database(env)
    values = env.read()
    assert values["PINECALL_VAULT_KEY"] == os.environ["PINECALL_VAULT_KEY"]
    assert values[database.RUNNER_KEY] != FORGOTTEN
    async with sessions() as session:
        with box_wide():
            assert await actor.verify_key(session, values[database.RUNNER_KEY]) is not None
    sandbox = values[database.SANDBOX_FLEET_KEY]
    assert sandbox.startswith("pc_fleet_") and values[database.WORKER_KEY] == sandbox
    assert database.PRODUCTION_FLEET_KEY not in values
    assert values[database.RUNNER_ENGINE[0]] == database.RUNNER_ENGINE[1]
    # Known now: run again, every key kept; a server asks for its production fleet's too.
    await database.prepare_database(env, production_fleet=True)
    again = env.read()
    assert {name: again[name] for name in values} == values
    assert again[database.PRODUCTION_FLEET_KEY].startswith("pc_fleet_")
