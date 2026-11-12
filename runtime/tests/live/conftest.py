"""One gateway's live side for a test: built as the lifespan builds it, on connections of the test's own."""

import os
from collections.abc import AsyncGenerator, AsyncIterator
from contextlib import AsyncExitStack, asynccontextmanager
from dataclasses import dataclass

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from runtime import builders
from runtime.alerts.service.alerts import Alerting
from runtime.calls.service import Prompts
from runtime.config import load_settings
from runtime.handles import Handles
from runtime.kit.crypto import Vault
from runtime.kit.loops import Loops
from runtime.live.parts import LiveParts
from runtime.live.service.apps import AppSockets
from runtime.live.service.whatsapp import Threads
from runtime.mail.service.outbox import Outbox
from runtime.signal import LocalSignal, Signal
from tests.fakes.livekit import per_world


@dataclass(frozen=True, slots=True)
class Side:
    """A gateway's live side as the lifespan builds it: its parts, its WhatsApp threads, what opens an app socket."""

    parts: LiveParts
    threads: Threads
    apps: AppSockets


def nowhere(asked: httpx.Request) -> httpx.Response:
    """What the internet answers a gateway that should have asked it nothing."""
    return httpx.Response(404, text=f"a test's gateway asked {asked.url}")


# The gateway of the suite (`gateway`) is reached as an SDK reaches it. This is a gateway's live side
# held in the test's hands, for what no request shows: a pass of the reaper, a call parked and taken,
# what two gateways tell each other. Its database is the suite's; its signal is the one it is given,
# which the suite's gateways are not on, so they hear nothing of it.
@asynccontextmanager
async def a_live_side(
    engine: AsyncEngine, sessions: async_sessionmaker[AsyncSession], signal: Signal
) -> AsyncGenerator[Side]:
    """A gateway's live side on the test database and the signal given, with a LiveKit of each env's own."""
    servers = per_world()
    vault = Vault(os.environ["PINECALL_VAULT_KEY"])
    async with AsyncExitStack() as stack:
        http = await stack.enter_async_context(httpx.AsyncClient(transport=httpx.MockTransport(nowhere)))
        handles = Handles(load_settings(), vault, http, servers, signal, engine, sessions)
        _, store, _, feeds, logs = builders.build_log_engine(handles, stack)
        loops = Loops()
        stack.push_async_callback(loops.stop)
        outbox = Outbox(sessions, vault, None)
        stack.push_async_callback(outbox.drain)
        _, offering = await builders.build_fleet(handles, feeds, loops, stack)
        alerting = Alerting(logs, outbox, None)
        parts = await builders.build_live_side(handles, stack, (store, logs, feeds, Prompts()), offering, alerting)
        threads = await builders.build_threads(parts, stack)
        codes = builders.build_codes(handles, logs)
        yield Side(parts, threads, AppSockets(parts, threads, codes.claim_heard))
    for server in servers.values():
        await server.aclose()


@pytest.fixture
async def side(engine: AsyncEngine, sessions: async_sessionmaker[AsyncSession]) -> AsyncIterator[Side]:
    """One gateway's live side, on a signal nobody else is on."""
    async with a_live_side(engine, sessions, LocalSignal()) as built:
        yield built


@pytest.fixture
def live(side: Side) -> LiveParts:
    """The parts of that gateway's live side."""
    return side.parts


@pytest.fixture
async def two_gateways(
    engine: AsyncEngine, sessions: async_sessionmaker[AsyncSession]
) -> AsyncIterator[tuple[LiveParts, LiveParts]]:
    """Two gateways of one box: each its own live side, both on one signal, as production's two are."""
    signal = LocalSignal()
    async with a_live_side(engine, sessions, signal) as one, a_live_side(engine, sessions, signal) as other:
        yield one.parts, other.parts
