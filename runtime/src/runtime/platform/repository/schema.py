"""The schema itself, on one connection: the SQL history it ran, its tables, its roles and grants."""

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from runtime.exceptions import ServiceUnavailable

# The previous runtime's bookkeeping of its SQL history, which Alembic's baseline follows on from.
HISTORY_TABLE = text("""
create table if not exists schema_migrations (
    name       text primary key,
    applied_at timestamptz not null default now(),
    sha256     text
)
""")
APPLIED = text("select name, sha256 from schema_migrations order by name")
RECORD = text("insert into schema_migrations (name, sha256) values (:name, :sha256)")
A_TABLE = text("select to_regclass(:name) is not null")
A_ROLE = text("select 1 from pg_roles where rolname = :role")
# Serializes concurrent runs; any constant no other code in the database uses.
NO_DRIVER = "the connection to Postgres closed while the schema was migrated"
SCHEMA_LOCK = text("select pg_advisory_xact_lock(2654190609)")
# Held on a connection of its own for a whole `migrate up`, history and revisions both.
RUN_LOCK = text("select pg_advisory_lock(2654190610)")
RUN_UNLOCK = text("select pg_advisory_unlock(2654190610)")
# The rows of every table and the sequences behind them, now and for every table the owner makes
# later (a day of call_log among them); never a table's shape, never TRUNCATE.
GRANTS = (
    "grant usage on schema public to {role}",
    "grant select, insert, update, delete on all tables in schema public to {role}",
    "grant usage, select, update on all sequences in schema public to {role}",
    "alter default privileges in schema public grant select, insert, update, delete on tables to {role}",
    "alter default privileges in schema public grant usage, select, update on sequences to {role}",
)


class SchemaRepository:
    """The schema itself, on one connection: the SQL history it ran, its tables, its grants."""

    def __init__(self, connection: AsyncConnection) -> None:
        self.connection = connection

    async def lock(self) -> None:
        """Hold the schema for this transaction, against any other run; no timeout cuts it."""
        await self.connection.execute(SCHEMA_LOCK)
        await self.connection.execute(text("set local statement_timeout = 0"))
        await self.connection.execute(text("set local lock_timeout = '1s'"))

    # The lock is the session's, so the connection holding it must sit in no transaction: one left open
    # is cut after a minute idle (`idle_in_transaction_session_timeout`) and the lock goes with it,
    # while the history still runs. The caller hands a connection in autocommit.
    async def hold_the_run(self) -> None:
        """Wait for any other run to finish, then hold the run until `release_the_run`."""
        await self.connection.execute(text("set statement_timeout = 0"))
        await self.connection.execute(RUN_LOCK)

    async def release_the_run(self) -> None:
        """Let the next run go."""
        await self.connection.execute(RUN_UNLOCK)

    async def has_table(self, name: str) -> bool:
        """Whether the table exists."""
        return bool((await self.connection.execute(A_TABLE, {"name": name})).scalar_one())

    async def history(self) -> dict[str, str | None]:
        """Each file of the SQL history the database ran, and the sha256 it ran."""
        await self.connection.execute(HISTORY_TABLE)
        rows = (await self.connection.execute(APPLIED)).all()
        return {str(name): None if sha256 is None else str(sha256) for name, sha256 in rows}

    async def run_file(self, name: str, statements: str, sha256: str) -> None:
        """Run one file of the history whole, and record it."""
        driver = (await self.connection.get_raw_connection()).driver_connection
        if driver is None:
            raise ServiceUnavailable(NO_DRIVER)
        # asyncpg's simple protocol, the one that takes several statements at once.
        await driver.execute(statements)
        await self.connection.execute(RECORD, {"name": name, "sha256": sha256})

    async def has_role(self, role: str) -> bool:
        """Whether the role exists."""
        return (await self.connection.execute(A_ROLE, {"role": role})).first() is not None

    async def grant_rows(self, role: str) -> None:
        """Grant the role every table's rows and nothing else."""
        quoted = '"' + role.replace('"', '""') + '"'
        for grant in GRANTS:
            await self.connection.execute(text(grant.format(role=quoted)))
