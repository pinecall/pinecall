"""What a verb runs with, and how an async verb becomes a Typer command with one way to fail."""

import asyncio
import functools
import logging
import sys
from collections.abc import Awaitable, Callable
from contextlib import AsyncExitStack
from functools import cached_property

import typer
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from runtime import builders
from runtime.cli.client import OpsClient
from runtime.cli.output import Printer
from runtime.config import Settings
from runtime.exceptions import ConfigurationError, PinecallError
from runtime.handles import Handles
from runtime.kit.crypto import Vault
from runtime.mail.service.outbox import Outbox
from runtime.postgres import create_engine, session_maker

logger = logging.getLogger(__name__)

# A verb's exit: 0 did it, 1 refused or found something wrong, 2 the settings or the arguments.
OK = 0
FOUND_WRONG = 1
MISCONFIGURED = 2

# A verb that reads the database alone holds a pool this small.
A_VERBS_POOL = 3


# Opened on first use, closed after the verb: a verb that reads a file opens nothing, and one that reads
# the database alone opens neither LiveKit nor Redis. What reaches past Postgres is the process's own
# state, built by the one constructor the gateway's lifespan builds it with (G-1).
class Context:
    """What a verb runs with: the settings, the printer, and the connections it asks for."""

    def __init__(self, settings: Settings, out: Printer) -> None:
        """Nothing opened yet."""
        self.settings = settings
        self.out = out
        self.stack = AsyncExitStack()
        self._handles: Handles | None = None

    @cached_property
    def engine(self) -> AsyncEngine:
        """The database, disposed of after the verb."""
        engine = create_engine(self.settings, pool_size=A_VERBS_POOL)
        self.stack.push_async_callback(engine.dispose)
        return engine

    @cached_property
    def sessions(self) -> async_sessionmaker[AsyncSession]:
        """Sessions on the database."""
        return session_maker(self.engine)

    @cached_property
    def vault(self) -> Vault:
        """The vault PINECALL_VAULT_KEY opens; refused in one sentence when unset."""
        key = self.settings.vault_key
        return Vault(None if key is None else key.get_secret_value())

    async def handles(self) -> Handles:
        """Everything a service reaching outside Postgres is handed, as the gateway's lifespan builds it."""
        if self._handles is None:
            self._handles = await builders.open_connections(self.settings, self.stack)
        return self._handles

    def outbox(self) -> Outbox:
        """The box's mailbox, sending at once; an email that cannot go is said, never queued."""
        return Outbox(self.sessions, self.vault, builders.read_box_mailbox(self.settings))

    async def ops(self) -> OpsClient:
        """The gateway's operator endpoints, opened with PINECALL_OPS_KEY; refused without one."""
        if self.settings.ops_key is None:
            raise ConfigurationError(
                "PINECALL_OPS_KEY is not set: the operator's endpoints are closed, and this verb speaks nothing else"
            )
        client = OpsClient(self.settings.gateway_url, self.settings.ops_key.get_secret_value())
        return await self.stack.enter_async_context(client)


def context_of(ctx: typer.Context) -> Context:
    """The context the root command put on Typer's."""
    found: Context = ctx.obj
    return found


# Typer runs sync functions; a verb is async, so it runs on a loop of its own, its connections
# closed after it, and its refusal is said in one sentence with the exit it means.
def verb[**P](run: Callable[P, Awaitable[int]]) -> Callable[P, None]:
    """An async verb as a Typer command: run on its own loop, every failure one line and an exit."""

    @functools.wraps(run)
    def command(*args: P.args, **kwargs: P.kwargs) -> None:
        raise typer.Exit(code=run_verb(run, *args, **kwargs))

    return command


def run_verb[**P](run: Callable[P, Awaitable[int]], *args: P.args, **kwargs: P.kwargs) -> int:
    """Run an async verb to its exit, its connections closed after it, a refusal said in one line."""
    ctx = next((arg for arg in args if isinstance(arg, typer.Context)), None)
    context = None if ctx is None else context_of(ctx)

    async def with_connections() -> int:
        if context is None:
            return await run(*args, **kwargs)
        async with context.stack:
            return await run(*args, **kwargs)

    try:
        return asyncio.run(with_connections())
    except ConfigurationError as refused:
        sys.stderr.write(f"pinecall-runtime: {refused}\n")
        return MISCONFIGURED
    except PinecallError as refused:
        sys.stderr.write(f"pinecall-runtime: {refused}\n")
        return FOUND_WRONG
    except KeyboardInterrupt:
        return FOUND_WRONG
