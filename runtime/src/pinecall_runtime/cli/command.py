"""What a verb runs with, and how an async verb becomes a Typer command with one way to fail."""

import asyncio
import functools
import logging
import sys
from collections.abc import Awaitable, Callable
from contextlib import AsyncExitStack
from functools import cached_property

import httpx
import typer
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from pinecall_runtime.accounts.service.mail import Outbox, parse_mailbox_url
from pinecall_runtime.cli.client import OpsClient
from pinecall_runtime.cli.output import Printer
from pinecall_runtime.config import Settings
from pinecall_runtime.exceptions import ConfigurationError, PinecallError
from pinecall_runtime.kit.crypto import Vault
from pinecall_runtime.kit.handles import Handles
from pinecall_runtime.livekit import Servers, open_servers
from pinecall_runtime.postgres import create_engine, session_maker
from pinecall_runtime.redis import Signal, open_signal

logger = logging.getLogger(__name__)

# A verb's exit: 0 did it, 1 refused or found something wrong, 2 the settings or the arguments.
OK = 0
FOUND_WRONG = 1
MISCONFIGURED = 2

NO_OPS_KEY = "PINECALL_OPS_KEY is not set: the operator's endpoints are closed, and this verb speaks nothing else"


# Opened on first use, closed after the verb: a verb that reads a file opens nothing.
class Context:
    """What a verb runs with: the settings, the printer, and the connections it asks for."""

    def __init__(self, settings: Settings, out: Printer) -> None:
        """Nothing opened yet."""
        self.settings = settings
        self.out = out
        self.stack = AsyncExitStack()
        self._http: httpx.AsyncClient | None = None
        self._servers: Servers | None = None
        self._signal: Signal | None = None
        self._handles: Handles | None = None

    @cached_property
    def engine(self) -> AsyncEngine:
        """The database, disposed of after the verb."""
        engine = create_engine(self.settings, pool_size=3)
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

    async def http(self) -> httpx.AsyncClient:
        """An HTTP client, closed after the verb."""
        if self._http is None:
            self._http = await self.stack.enter_async_context(httpx.AsyncClient())
        return self._http

    async def servers(self) -> Servers:
        """Each env's LiveKit, closed after the verb."""
        if self._servers is None:
            self._servers = await self.stack.enter_async_context(open_servers(self.settings))
        return self._servers

    async def signal(self) -> Signal:
        """What the gateways tell each other (Redis, or this process alone), closed after the verb."""
        if self._signal is None:
            self._signal = await self.stack.enter_async_context(open_signal(self.settings))
        return self._signal

    async def handles(self) -> Handles:
        """Everything a service reaching outside Postgres is handed, as the gateway hands it."""
        if self._handles is None:
            http = await self.http()
            self._handles = Handles(
                self.settings, self.vault, http, await self.servers(), await self.signal(), self.sessions
            )
        return self._handles

    async def outbox(self) -> Outbox:
        """The box's mailbox, sending at once; an email that cannot go is said, never queued."""
        url = self.settings.smtp_url
        mailbox = None if url is None else parse_mailbox_url(url.get_secret_value(), self.settings.mail_from or "")
        return Outbox(self.sessions, self.vault, mailbox)

    @property
    def base_url(self) -> str:
        """The address a link the box makes points at: its public name, else the gateway's URL."""
        return self.settings.address or self.settings.gateway_url.rstrip("/")

    async def ops(self) -> OpsClient:
        """The gateway's operator endpoints, opened with PINECALL_OPS_KEY; refused without one."""
        if self.settings.ops_key is None:
            raise ConfigurationError(NO_OPS_KEY)
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
        raise typer.Exit(code=_ran(run, *args, **kwargs))

    return command


def _ran[**P](run: Callable[P, Awaitable[int]], *args: P.args, **kwargs: P.kwargs) -> int:
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
