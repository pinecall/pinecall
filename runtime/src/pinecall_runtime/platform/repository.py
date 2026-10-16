"""The box_settings table, one JSON value per name; what Postgres says of its standbys; the schema."""

from datetime import datetime
from typing import Any

from sqlalchemy import text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncConnection

from pinecall_runtime.exceptions import ServiceUnavailable
from pinecall_runtime.kit.repository import Repository
from pinecall_runtime.kit.time import now
from pinecall_runtime.platform.models import BoxSetting


class BoxSettingRepository(Repository[BoxSetting]):
    """Named settings of the box."""

    model = BoxSetting

    async def get(self, name: str) -> BoxSetting | None:
        """The row by name."""
        return await self.one_or_none(self.statement().where(BoxSetting.name == name))

    async def put(self, name: str, value: dict[str, Any], ciphertext: str | None = None) -> BoxSetting:
        """Set the value whole; the ciphertext beside it where part of the value is a secret."""
        row = await self.get(name)
        if row is None:
            return await self.add(BoxSetting(name=name, value=value, ciphertext=ciphertext))
        return await self.update(row, value=value, ciphertext=ciphertext, set_at=now())

    # One statement, so two processes seeding at once never both think they were first.
    async def put_if_absent(self, name: str, value: dict[str, Any]) -> bool:
        """Set the value only where nobody set one; whether it was set."""
        statement = (
            insert(BoxSetting)
            .values(name=name, value=value, set_at=now())
            .on_conflict_do_nothing(index_elements=[BoxSetting.name])
            .returning(BoxSetting.name)
        )
        return (await self.session.execute(statement)).scalar_one_or_none() is not None

    async def remove(self, name: str) -> bool:
        """Forget the setting; whether there was one."""
        row = await self.get(name)
        if row is None:
            return False
        await self.delete(row)
        return True


# A lag never replayed yet (a replica caught up and idle) reads as zero.
REPLICAS = text("""
select application_name as replica, extract(epoch from coalesce(replay_lag, interval '0')) as lag
from pg_stat_replication
""")


class ReplicationRepository(Repository[BoxSetting]):
    """How far behind each standby is in replaying the primary's WAL."""

    model = BoxSetting

    async def lags(self) -> list[tuple[str, float]]:
        """Each standby by name, and its replay lag in seconds."""
        rows = (await self.session.execute(REPLICAS)).all()
        return [(str(replica), float(lag)) for replica, lag in rows]


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


# What Postgres says of its archiving, and of the spool a box ships its WAL from.
ARCHIVER = text("""
select current_setting('archive_mode') as mode, last_archived_time, last_failed_time, last_failed_wal
from pg_stat_archiver
""")
# Read through Postgres, which has the spool mounted: the doctor's own user reads no WAL.
SPOOLED = text("""
select count(*) as waiting, min(file.modification) as oldest
from pg_ls_dir(:spool, true, false) as name,
     lateral pg_stat_file(:spool || '/' || name, true) as file
where not file.isdir and name not like '%.part'
""")


class ArchiveRepository(Repository[BoxSetting]):
    """The archiver's state and the spool's backlog."""

    model = BoxSetting

    async def archiver(self) -> tuple[str, datetime | None, datetime | None, str | None] | None:
        """The archive mode, when a segment last shipped, when one last failed, and which."""
        row = (await self.session.execute(ARCHIVER)).first()
        if row is None:
            return None
        mode, archived, failed, wal = row
        return str(mode), archived, failed, None if wal is None else str(wal)

    async def spooled(self, spool: str) -> tuple[int, datetime | None]:
        """How many segments wait in the spool, and the oldest's modification time."""
        waiting, oldest = (await self.session.execute(SPOOLED, {"spool": spool})).one()
        return int(waiting), oldest
