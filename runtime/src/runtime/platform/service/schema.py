"""The schema: the previous runtime's SQL history where a database lacks it, then Alembic's revisions."""

import asyncio
import hashlib
import warnings
from dataclasses import dataclass
from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from alembic.util import CommandError
from sqlalchemy import Connection
from sqlalchemy.exc import SAWarning
from sqlalchemy.ext.asyncio import AsyncEngine

from runtime.exceptions import ConfigurationError
from runtime.kit.retry import until
from runtime.platform.repository.schema import SchemaRepository

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

    async def grant() -> bool | None:
        async with engine.begin() as connection:
            schema = SchemaRepository(connection)
            if not await schema.has_role(role):
                return None
            await schema.grant_rows(role)
            return True

    if await until(grant, every_s=ROLE_ASKED_EVERY_S, within_s=ROLE_WAITED_S) is None:
        raise ConfigurationError(NO_ROLE.format(role=role, waited=ROLE_WAITED_S))


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


async def standing_of(engine: AsyncEngine) -> Standing:
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
    async with engine.connect() as raw:
        # Autocommit: the connection that holds the run sits in no transaction while the history and
        # the revisions run on others, so no idle-in-transaction timeout takes the lock from it.
        connection = await raw.execution_options(isolation_level="AUTOCOMMIT")
        schema = SchemaRepository(connection)
        await schema.hold_the_run()
        try:
            history = await apply_history(engine)
            # Alembic runs a loop of its own (migrations/env.py): off this one, in a thread.
            await asyncio.to_thread(upgrade_schema, tracked=history.tracked)
        finally:
            await schema.release_the_run()
    return history, await standing_of(engine)


# Alembic's own comparison, in its own environment (`migrations/env.py`): a table, a column or an
# index a model declares and no revision makes, or one a revision made and no model shows. Not run
# on a loop: the environment runs one of its own.
def find_drift() -> str | None:
    """What Alembic would generate against the settings' database; None when the models are the schema."""
    try:
        # What SQLAlchemy says while it reflects a table (a check constraint's options it cannot
        # place) is not a difference: a process that makes warnings errors would stop on it.
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", SAWarning)
            command.check(_config())
    except CommandError as differs:
        return str(differs)
    return None


def list_steps() -> list[str]:
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
