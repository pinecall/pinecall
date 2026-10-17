"""The database: the engine, a session per request, and row-level security scoped to an org."""

import asyncio
import contextvars
from collections.abc import AsyncGenerator, Coroutine, Generator
from contextlib import asynccontextmanager, contextmanager
from contextvars import ContextVar
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy import Connection, event, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import Session as SyncSession
from sqlalchemy.orm import SessionTransaction
from sqlalchemy.pool import QueuePool

from pinecall_runtime.config import Settings

# Row-level security (migration 0096): a transaction that names an org sees and writes that org's
# rows alone; one that names none is the box's, as the operator's endpoints and the loops are. The
# gateway names the org of the actor's key for the whole request.
SCOPED_ORG: ContextVar[str | None] = ContextVar("scoped_org", default=None)

# Transaction-local, so a pooled connection goes back as it came.
SCOPE = text("select set_config('pinecall.org', :org, true)")

# A statement past this is cancelled; what is long on purpose runs in `unbounded`.
STATEMENT_TIMEOUT_MS = 30_000
IDLE_IN_TRANSACTION_MS = 60_000
CONNECT_TIMEOUT_S = 10
POOL_WAIT_S = 2.0


# The one name an endpoint catches of the database's: a scrape or a health line that must still
# answer when Postgres does not.
DatabaseError = SQLAlchemyError


# A task cancelled while it waits on Postgres gets its CancelledError back wrapped in the driver's
# error: a loop that caught the error and went on would never end, and its process never stop.
def is_cancellation(error: BaseException) -> bool:
    """Whether a database error is the task's own cancellation, which a loop lets through."""
    seen: BaseException | None = error
    for _ in range(8):
        if seen is None:
            return False
        if isinstance(seen, asyncio.CancelledError):
            return True
        seen = getattr(seen, "orig", None) or seen.__cause__ or seen.__context__
    return False


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


def session_maker(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    """Sessions on the engine: no autoflush surprises, objects usable after commit."""
    maker = async_sessionmaker(engine, expire_on_commit=False, autoflush=False)
    event.listen(SyncSession, "after_begin", _scope_transaction)
    return maker


# Runs on the sync side of every transaction begun by any session: the org the request acts for is
# set for that transaction alone. A task of the box's names none and the statement is skipped.
def _scope_transaction(_session: SyncSession, _transaction: SessionTransaction, connection: Connection) -> None:
    org = SCOPED_ORG.get()
    if org is not None:
        connection.execute(SCOPE, {"org": org})


def scope_to(org: str) -> None:
    """Name the org every transaction begun from here on in this request acts for."""
    SCOPED_ORG.set(org)


@contextmanager
def box_wide() -> Generator[None]:
    """Act as the box within the block: a tenant's request reading across orgs on purpose."""
    token = SCOPED_ORG.set(None)
    try:
        yield
    finally:
        SCOPED_ORG.reset(token)


def box_task[T](work: Coroutine[object, object, T]) -> asyncio.Task[T]:
    """Start the work as a task of the box's, whatever org the request starting it acts for."""
    context = contextvars.copy_context()
    context.run(SCOPED_ORG.set, None)
    return asyncio.create_task(work, context=context)


@asynccontextmanager
async def unbounded(session: AsyncSession) -> AsyncGenerator[AsyncSession]:
    """The session's transaction with no statement or idle timeout: an erasure, an export, an index."""
    from sqlalchemy import text

    await session.execute(text("SET LOCAL statement_timeout = 0"))
    await session.execute(text("SET LOCAL idle_in_transaction_session_timeout = 0"))
    yield session


async def get_session(request: Request) -> AsyncGenerator[AsyncSession]:
    """One session per request, committed when the endpoint returns, rolled back when it raises."""
    maker: async_sessionmaker[AsyncSession] = request.app.state.sessions
    async with maker() as session:
        try:
            yield session
            await session.commit()
        except BaseException:
            await session.rollback()
            raise


# "function": committed and handed back when the endpoint returns, before its response is sent. A
# streamed answer (a log followed, an export) would otherwise hold the connection and an open
# transaction for as long as its reader stays.
Session = Annotated[AsyncSession, Depends(get_session, scope="function")]
