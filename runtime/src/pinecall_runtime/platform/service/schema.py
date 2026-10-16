"""The schema: the previous runtime's SQL history where a database lacks it, then Alembic's revisions."""

import asyncio
import hashlib
from dataclasses import dataclass
from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import Connection
from sqlalchemy.ext.asyncio import AsyncEngine

from pinecall_runtime.exceptions import ConfigurationError
from pinecall_runtime.platform.repository import SchemaRepository

MIGRATIONS = Path(__file__).resolve().parents[2] / "migrations"
HISTORY = MIGRATIONS / "sql"
# The revision that is the live schema the history made (migrations/versions/…_000000_…).
BASELINE = "000000"
ALEMBIC_TABLE = "alembic_version"

# CloudNativePG makes the role from its secret a few seconds after the chart says so: waited for.
ROLE_WAITED_S = 120.0
ROLE_ASKED_EVERY_S = 2.0

EDITED = (
    "migration {name} changed after it was applied: this database ran a different file "
    "(applied sha256 {was}, on disk {now}). The history is never edited: restore the file"
)
MISSING = "migration {name} is recorded as applied and is not in this distribution: it is older than the database"
NO_ROLE = (
    "role {role} does not exist after {waited:g} s: its secret (charts/postgres, the managed role) "
    "is not synced yet, or the role is named wrong; nothing was granted"
)


@dataclass(frozen=True, slots=True)
class History:
    """What the SQL history did to a database, and whether Alembic already tracked it."""

    applied: tuple[str, ...]
    tracked: bool


# One transaction, under a lock: a new database gets the whole history or none of it. A database
# the previous runtime migrated has run every file and gets none.
async def apply_history(engine: AsyncEngine) -> History:
    """Run the files of the SQL history the database has not run, in name order."""
    async with engine.begin() as connection:
        schema = SchemaRepository(connection)
        await schema.lock()
        tracked = await schema.has_table(ALEMBIC_TABLE)
        ran = await schema.history()
        files = {path.name: path for path in sorted(HISTORY.glob("*.sql"))}
        for name, was in ran.items():
            if name not in files:
                raise ConfigurationError(MISSING.format(name=name))
            now = _sha256(await asyncio.to_thread(files[name].read_bytes))
            if was is not None and was != now:
                raise ConfigurationError(EDITED.format(name=name, was=was, now=now))
        applied: list[str] = []
        for name, path in files.items():
            if name in ran:
                continue
            statements = await asyncio.to_thread(path.read_bytes)
            await schema.run_file(name, statements.decode("utf-8"), _sha256(statements))
            applied.append(name)
    return History(applied=tuple(applied), tracked=tracked)


# Alembic runs its own loop (migrations/env.py), so this is called outside one.
def upgrade_schema(*, tracked: bool) -> None:
    """Mark an untracked database as the baseline, then apply every revision after it."""
    config = _config()
    if not tracked:
        command.stamp(config, BASELINE)
    command.upgrade(config, "head")


# Granted again every run: a table a revision made is granted the moment it exists, and a grant
# taken away by hand comes back. Refused, not skipped, when the role never came: a gateway that
# connects as it would find nothing it may read.
async def grant_rows(engine: AsyncEngine, role: str) -> None:
    """Grant the role every table's rows and nothing else, once it exists."""
    waited = 0.0
    while True:
        async with engine.begin() as connection:
            schema = SchemaRepository(connection)
            if await schema.has_role(role):
                await schema.grant_rows(role)
                return
        if waited >= ROLE_WAITED_S:
            raise ConfigurationError(NO_ROLE.format(role=role, waited=ROLE_WAITED_S))
        await asyncio.sleep(ROLE_ASKED_EVERY_S)
        waited += ROLE_ASKED_EVERY_S


def _sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


@dataclass(frozen=True, slots=True)
class Standing:
    """Where a database stands: the history files it has not run, and the revisions it lacks."""

    history_pending: tuple[str, ...]
    current: str | None
    head: str | None

    @property
    def behind(self) -> bool:
        """Whether a run would change the database."""
        return bool(self.history_pending) or self.current != self.head


async def schema_standing(engine: AsyncEngine) -> Standing:
    """What `migrate up` would do to the database, nothing changed."""
    async with engine.connect() as connection:
        schema = SchemaRepository(connection)
        ran = await schema.history() if await schema.has_table("schema_migrations") else {}
        current = await connection.run_sync(_current_revision) if await schema.has_table(ALEMBIC_TABLE) else None
    files = tuple(path.name for path in sorted(HISTORY.glob("*.sql")) if path.name not in ran)
    return Standing(history_pending=files, current=current, head=_head())


# One run at a time: a second `migrate up` (two pods, a test suite's workers) waits on the first and
# then finds the history run and the revisions applied.
async def migrate_database(engine: AsyncEngine) -> tuple[History, Standing]:
    """Bring the database to this release: the history where it lacks it, then every revision."""
    async with engine.connect() as connection:
        schema = SchemaRepository(connection)
        await schema.hold_the_run()
        try:
            history = await apply_history(engine)
            # Alembic runs a loop of its own (migrations/env.py): off this one, in a thread.
            await asyncio.to_thread(upgrade_schema, tracked=history.tracked)
        finally:
            await schema.release_the_run()
    return history, await schema_standing(engine)


def planned_steps() -> list[str]:
    """Every step a run applies to an empty database, in order: the history's files, then the revisions."""
    files = [path.name for path in sorted(HISTORY.glob("*.sql"))]
    script = ScriptDirectory.from_config(_config())
    revisions = list(script.walk_revisions())
    revisions.reverse()
    return [*files, *(f"{each.revision}  {_title(each.doc)}".rstrip() for each in revisions)]


def _title(doc: str | None) -> str:
    return doc.splitlines()[0] if doc else ""


def _config() -> Config:
    config = Config()
    config.set_main_option("script_location", str(MIGRATIONS))
    return config


def _head() -> str | None:
    return ScriptDirectory.from_config(_config()).get_current_head()


def _current_revision(connection: Connection) -> str | None:
    return MigrationContext.configure(connection).get_current_revision()
