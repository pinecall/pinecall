"""A machine's database brought to this release, and the box's own keys a runtime runs on, drawn once."""

import asyncio
import os
import secrets

from sqlalchemy.ext.asyncio import AsyncEngine

from runtime.accounts.models import BOX_ORG
from runtime.accounts.service import actor, keys, orgs
from runtime.cli.setup.env_file import EnvFile, settings_of
from runtime.enums import Env, KeyScope
from runtime.platform.service import schema
from runtime.postgres import create_engine, session_maker
from runtime.scoping import box_wide

# A release deployed here runs as a process of this machine: the code is its owner's own.
RUNNER_ENGINE = ("PINECALL_RUNNER_ENGINE", "processes")
# A fleet's key is a secret drawn outside the runtime, given to the gateway and to that env's workers
# (R11): here, drawn into the settings file once. The sandbox worker reads its fleet's as its own key.
SANDBOX_FLEET_KEY = "PINECALL_SANDBOX_FLEET_KEY"
PRODUCTION_FLEET_KEY = "PINECALL_PRODUCTION_FLEET_KEY"
WORKER_KEY = "PINECALL_WORKER_KEY"
# The runner's key is a row of the box's own org: drawn again when the database forgot it.
RUNNER_KEY = "PINECALL_RUNNER_KEY"
A_RUNNER_KEY = "the sandbox runner"
# The box's own org, where the runner's key is minted, made with the database.
BOX_ORG_NAME = "Pinecall"
A_FLEET_KEY_BYTES = 32


async def prepare_database(env: EnvFile, *, production_fleet: bool = False) -> schema.History:
    """The schema at this release; the box's org, the fleets' keys and the runner's, drawn once into the settings."""
    values = env.read()
    # The revisions read the process's own settings (`migrations/env.py`): the machine's settings become
    # the process's here, as they are its children's (a clean machine reached for localhost:5432, 2026-10-17).
    os.environ.update(values)
    engine = create_engine(settings_of(values), pool_size=3)
    try:
        history = await schema.apply_history(engine)
        await asyncio.to_thread(schema.upgrade_schema, tracked=history.tracked)
        runner = await _runner_key(engine, values.get(RUNNER_KEY))
    finally:
        await engine.dispose()
    drawn: dict[str, str | None] = {RUNNER_KEY: runner}
    sandbox = values.get(SANDBOX_FLEET_KEY) or _a_fleet_key()
    drawn |= {SANDBOX_FLEET_KEY: sandbox, WORKER_KEY: sandbox}
    if production_fleet:
        drawn[PRODUCTION_FLEET_KEY] = values.get(PRODUCTION_FLEET_KEY) or _a_fleet_key()
    if RUNNER_ENGINE[0] not in values:
        drawn[RUNNER_ENGINE[0]] = RUNNER_ENGINE[1]
    env.set(**drawn)
    return history


async def _runner_key(engine: AsyncEngine, kept: str | None) -> str:
    async with session_maker(engine).begin() as session:
        with box_wide():
            if kept is not None and await actor.verify_key(session, kept) is not None:
                return kept
            org = await orgs.find_org(session, BOX_ORG) or await orgs.create_org(session, BOX_ORG, BOX_ORG_NAME)
            issue = keys.Issue(org=org.id, env=Env.sandbox, scopes=frozenset({KeyScope.runner}), label=A_RUNNER_KEY)
            return (await keys.issue_key(session, issue)).key


def _a_fleet_key() -> str:
    return f"pc_fleet_{secrets.token_urlsafe(A_FLEET_KEY_BYTES)}"
