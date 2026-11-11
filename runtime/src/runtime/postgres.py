"""The database: the engine, the two sessions a request may ask for, and row-level security applied to each."""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Annotated, NewType

from fastapi import Depends
from sqlalchemy import Connection, Engine, event, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.exc import TimeoutError as PoolTimeout
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import Session as SyncSession
from sqlalchemy.orm import SessionTransaction
from sqlalchemy.pool import QueuePool
from starlette.requests import HTTPConnection

from runtime.config import Settings
from runtime.exceptions import ServiceUnavailable
from runtime.handles import sessions_of
from runtime.scoping import SCOPED_ORG

# Transaction-local, so a pooled connection goes back as it came.
SCOPE = text("select set_config('pinecall.org', :org, true)")
# On the connection: the session's transaction it scoped, the org it named there ('' the box), and whether
# that is pinned: a box-wide session stays the box's whatever org the request acts for.
SCOPED_AS = "pinecall.scoped_as"
# On a session's `info`: it is the box's, and names no org.
BOX_WIDE = "pinecall.box_wide"

# A statement past this is cancelled; what is long on purpose runs in `without_timeouts`.
STATEMENT_TIMEOUT_MS = 30_000
IDLE_IN_TRANSACTION_MS = 60_000
CONNECT_TIMEOUT_S = 10
POOL_WAIT_S = 2.0


# The one name an endpoint catches of the database's: a scrape or a health line that must still
# answer when Postgres does not.
DatabaseError = SQLAlchemyError

# What a request is told when every connection was taken for POOL_WAIT_S: the same sentence from
# an endpoint, the middleware that resolves its actor, and an app's socket. A worker retries a 503.
NO_CONNECTION = "the database is busy: no connection came free within {wait:g} s; try again"


def busy() -> ServiceUnavailable:
    """The refusal of a request that found no connection free in time."""
    return ServiceUnavailable(NO_CONNECTION.format(wait=POOL_WAIT_S))


def is_pool_timeout(error: BaseException) -> bool:
    """Whether a database error is the pool's: every connection taken for POOL_WAIT_S."""
    return isinstance(error, PoolTimeout)


def pool_measures(engine: AsyncEngine) -> tuple[int, int]:
    """The pool's size and how many of its connections are out; zeros on a pool that keeps none."""
    pool = engine.pool
    return (pool.size(), pool.checkedout()) if isinstance(pool, QueuePool) else (0, 0)


def create_engine(settings: Settings, *, pool_size: int | None = None) -> AsyncEngine:
    """The async engine on the settings' database, timeouts set, RLS applied per transaction."""
    engine = create_async_engine(
        settings.database_dsn(),
        pool_size=pool_size or settings.db_pool,
        max_overflow=0,
        pool_timeout=POOL_WAIT_S,
        pool_pre_ping=True,
        connect_args={
            "timeout": CONNECT_TIMEOUT_S,
            "server_settings": {
                "statement_timeout": str(STATEMENT_TIMEOUT_MS),
                "idle_in_transaction_session_timeout": str(IDLE_IN_TRANSACTION_MS),
                "application_name": f"pinecall-{settings.role}",
            },
        },
    )
    return engine


# The listener is the class's, so a process with two engines (the endpoints', the log writer's)
# registers it once: twice would name the org twice a transaction.
def session_maker(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    """Sessions on the engine: no autoflush surprises, objects usable after commit."""
    install_row_level_security()
    return async_sessionmaker(engine, expire_on_commit=False, autoflush=False)


def install_row_level_security() -> None:
    """Scope every transaction of every session to the org it acts for; installing twice changes nothing."""
    if not event.contains(SyncSession, "after_begin", _scope_transaction):
        event.listen(SyncSession, "after_begin", _scope_transaction)
    if not event.contains(Engine, "before_execute", _rescope_statement):
        event.listen(Engine, "before_execute", _rescope_statement)


# Runs on the sync side of every transaction begun by any session: the org the request acts for is
# set for that transaction alone. A task of the box's names none and the statement is skipped.
def _scope_transaction(session: SyncSession, _transaction: SessionTransaction, connection: Connection) -> None:
    pinned = bool(session.info.get(BOX_WIDE))
    org = None if pinned else SCOPED_ORG.get()
    connection.info[SCOPED_AS] = (connection.get_transaction(), org or "", pinned)
    if org is not None:
        connection.execute(SCOPE, {"org": org})


# The setting is the transaction's, set as it began: `box_wide` entered after a request's first
# statement would still read its org alone, and a statement after the block would still read every
# org. Before each statement of a session's transaction, the org it acts for now is named again
# where it changed. A connection used outside a session's transaction is left as it is.
def _rescope_statement(connection: Connection, statement: object, *_args: object) -> None:
    scoped = connection.info.get(SCOPED_AS)
    if statement is SCOPE or scoped is None or scoped[2] or scoped[0] is not connection.get_transaction():
        return
    org = SCOPED_ORG.get() or ""
    if scoped[1] != org:
        connection.info[SCOPED_AS] = (scoped[0], org, False)
        connection.execute(SCOPE, {"org": org})


@asynccontextmanager
async def without_timeouts(session: AsyncSession) -> AsyncGenerator[AsyncSession]:
    """The session's transaction with no statement or idle timeout: an erasure, an export, an index."""
    await session.execute(text("SET LOCAL statement_timeout = 0"))
    await session.execute(text("SET LOCAL idle_in_transaction_session_timeout = 0"))
    yield session


async def get_session(connection: HTTPConnection) -> AsyncGenerator[AsyncSession]:
    """One session of the request's org, committed when the endpoint returns, rolled back when it raises."""
    async with sessions_of(connection)() as session:
        try:
            yield session
            await session.commit()
        except BaseException:
            await session.rollback()
            raise


# The same connection pool, the other reach: a route asks for one of the two, never both, or under load
# every request holds one connection and waits for its second.
BoxSession = NewType("BoxSession", AsyncSession)


async def get_box_session(connection: HTTPConnection) -> AsyncGenerator[BoxSession]:
    """One session of the box's: it names no org, whatever org the request acts for."""
    async with sessions_of(connection)(info={BOX_WIDE: True}) as session:
        try:
            yield BoxSession(session)
            await session.commit()
        except BaseException:
            await session.rollback()
            raise


# "function": committed and handed back when the endpoint returns, before its response is sent. A
# streamed answer (a log followed, an export) would otherwise hold the connection and an open
# transaction for as long as its reader stays.
Session = Annotated[AsyncSession, Depends(get_session, scope="function")]
TheBoxSession = Annotated[BoxSession, Depends(get_box_session, scope="function")]
