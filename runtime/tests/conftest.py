"""What the suites share: the test database migrated once, the gateway served, and a fresh tenant per test."""

import asyncio
import contextlib
import json
import os
import secrets
import time
from collections.abc import AsyncGenerator, AsyncIterator, Callable, Mapping
from contextlib import asynccontextmanager
from dataclasses import dataclass
from uuid import uuid4

import httpx
import pytest
import uvicorn
from cryptography.fernet import Fernet
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker
from websockets.asyncio.client import ClientConnection, connect

# Read by the settings at import of anything that loads them: one set for the whole run, so the
# vault that seals a key in a fixture opens it in the gateway.
os.environ.setdefault("PINECALL_VAULT_KEY", Fernet.generate_key().decode())
os.environ.setdefault("PINECALL_TOKEN_KEY", "a-token-key-for-the-suite")
os.environ.setdefault("PINECALL_OPS_KEY", "the-suites-own-ops-key")
os.environ.setdefault("LIVEKIT_API_KEY", "devkey")
os.environ.setdefault("LIVEKIT_API_SECRET", "a-suite-only-livekit-secret-0123456789")

from pinecall_runtime.accounts.service import keys, members, orgs
from pinecall_runtime.app import create_app
from pinecall_runtime.calls.store import Store
from pinecall_runtime.config import load_settings
from pinecall_runtime.enums import Env, KeyScope, Role
from pinecall_runtime.exceptions import Conflict
from pinecall_runtime.jobs.service.client import GatewayClient, gateway_at
from pinecall_runtime.kit.crypto import Vault
from pinecall_runtime.kit.text import JsonObject
from pinecall_runtime.platform import service as platform
from pinecall_runtime.postgres import create_engine, session_maker
from pinecall_runtime.providers import service as providers
from pinecall_runtime.wire.commands import AgentRegister
from tests.fakes import acme as fake_acme

fake_acme.install()

needs_the_database = pytest.mark.skipif("DATABASE_URL" not in os.environ, reason="the test database")
needs_the_services = pytest.mark.skipif(
    "DATABASE_URL" not in os.environ or "PINECALL_REDIS_URL" not in os.environ,
    reason="the test database and Redis",
)

THE_OPS_KEY = os.environ["PINECALL_OPS_KEY"]
A_PASSWORD = "a-password-for-the-suite"
# The box's catalog for the whole run: every stage on acme, the model priced so a call's cost is a
# number a test can name.
THE_CATALOG = providers.Catalog.model_validate(
    {
        "defaults": {
            "llm": {"vendor": fake_acme.ACME, "model": fake_acme.MODEL},
            "stt": {"vendor": fake_acme.ACME, "model": fake_acme.EARS},
            "tts": {"vendor": fake_acme.ACME, "model": fake_acme.VOICE},
        },
        "rates": {fake_acme.MODEL: {"input": 1.0, "output": 2.0, "as_of": "2026-10-16"}},
    }
)


# A catalog a test hands to the code it calls, never the box's row: the model answers the script.
def configured(replies: list[list[str | dict[str, object]]] | None = None) -> providers.Catalog:
    """Every stage on acme, its model answering these replies in order."""
    return providers.Catalog.model_validate(
        {
            "defaults": {
                "llm": {"vendor": fake_acme.ACME, "model": fake_acme.MODEL},
                "stt": {"vendor": fake_acme.ACME, "model": fake_acme.EARS},
                "tts": {"vendor": fake_acme.ACME, "model": fake_acme.VOICE},
            },
            "tuning": {f"llm/{fake_acme.ACME}": {"options": {"replies": replies or []}}},
            "rates": {fake_acme.MODEL: {"input": 1.0, "output": 2.0, "as_of": "2026-10-16"}},
        }
    )


@dataclass(frozen=True)
class Tenant:
    """An org of this test alone: its admin, the admin's key, and a server's key in the sandbox."""

    org: str
    slug: str
    member: str
    person_key: str
    server_key: str

    @property
    def person(self) -> dict[str, str]:
        """The admin's headers, in the sandbox."""
        return {"authorization": f"Bearer {self.person_key}", "pinecall-env": Env.sandbox.value}

    @property
    def server(self) -> dict[str, str]:
        """The server key's headers."""
        return {"authorization": f"Bearer {self.server_key}"}


BOX = {"authorization": f"Bearer {THE_OPS_KEY}"}


@pytest.fixture(scope="session")
async def engine() -> AsyncIterator[AsyncEngine]:
    """The test database, migrated to this release once per worker (`migrate up` takes a lock)."""
    if "DATABASE_URL" not in os.environ:
        pytest.skip("the test database")
    made = create_engine(load_settings(), pool_size=5)
    await platform.migrate_database(made)
    # Every worker tries; the first one writes it, and the others are told it is there.
    with contextlib.suppress(Conflict):
        async with session_maker(made).begin() as session:
            await providers.seed_catalog(session, THE_CATALOG)
    # The box holds acme's key and lends it, as admission lends every key by default.
    async with session_maker(made).begin() as session:
        await providers.put_box_credentials(
            session, Vault(os.environ["PINECALL_VAULT_KEY"]), fake_acme.ACME, "acme-key"
        )
    yield made
    await made.dispose()


@pytest.fixture(scope="session")
def sessions(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    """Sessions on the migrated database, as the services take them."""
    return session_maker(engine)


async def make_tenant(sessions: async_sessionmaker[AsyncSession]) -> Tenant:
    """A fresh org, its first admin seated with a password, the admin's key and a server's key."""
    slug = f"suite-{secrets.token_hex(5)}"
    async with sessions.begin() as session:
        org = await orgs.create_org(session, slug, "The suite's org")
        invitee = members.Invitee(f"admin@{slug}.test", "The admin", Role.admin)
        link = await members.invite(session, org.id, invitee, seats=None, vouched=True)
    async with sessions.begin() as session:
        seated = await members.accept_link(session, link.token, A_PASSWORD, 8)
        assert seated is not None, "the invitation did not seat the admin"
        _, person_key = await keys.issue_person_key(session, seated, label="the suite")
        issue = keys.Issue(org=org.id, env=Env.sandbox, scopes=keys.SERVER_SCOPES, label="the suite's server")
        _, server_key = await keys.issue_key(session, issue)
    return Tenant(org=org.id, slug=slug, member=seated.id, person_key=person_key, server_key=server_key)


@pytest.fixture
async def tenant(sessions: async_sessionmaker[AsyncSession]) -> Tenant:
    """An org of this test alone."""
    return await make_tenant(sessions)


@dataclass(frozen=True)
class Gateway:
    """The gateway on a port of its own, reached over HTTP and WebSocket as an SDK reaches it."""

    url: str
    http: httpx.AsyncClient
    # The app served, for a test that plays the gateway losing what it held in memory.
    app: FastAPI

    def socket(self, path: str, headers: Mapping[str, str]) -> connect:
        """A WebSocket to the path, opened with these headers."""
        return connect(f"ws{self.url.removeprefix('http')}{path}", additional_headers=dict(headers))


# Served by uvicorn, as production serves it: an in-process transport cancels a socket's handler
# when the client lets go, and the seal that runs after a hang-up would never run.
@pytest.fixture(scope="session")
async def gateway(engine: AsyncEngine) -> AsyncIterator[Gateway]:
    """The gateway served on a free port of this worker, its lifespan on the test database."""
    if "PINECALL_REDIS_URL" not in os.environ:
        pytest.skip("Redis")
    app = create_app()
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=0, log_level="warning"))
    serving = asyncio.create_task(server.serve())
    while not server.started:
        if serving.done():
            serving.result()
        await asyncio.sleep(0.01)
    port = server.servers[0].sockets[0].getsockname()[1]
    url = f"http://127.0.0.1:{port}"
    async with httpx.AsyncClient(base_url=url, timeout=10.0) as http:
        yield Gateway(url, http, app)
    server.should_exit = True
    await serving


async def received(socket: ClientConnection, kind: str) -> JsonObject:
    """The frames a socket is sent, until one of this kind."""
    while True:
        frame: JsonObject = json.loads(await socket.recv())
        if frame["type"] == kind:
            return frame


# Tests read the clock, so it is one they can predict: 1.0, then half a second more each time.
FIRST_TICK = 1.0
A_TICK_S = 0.5


@pytest.fixture
def ticking() -> Callable[[], float]:
    """A clock that starts at FIRST_TICK and moves A_TICK_S on every reading."""
    readings = iter(FIRST_TICK + A_TICK_S * step for step in range(1_000_000))
    return lambda: next(readings)


@pytest.fixture
async def store(sessions: async_sessionmaker[AsyncSession], ticking: Callable[[], float]) -> AsyncIterator[Store]:
    """The store on the test database, stamping entries with the ticking clock; drained after."""
    opened = Store(sessions, clock=ticking)
    yield opened
    await opened.writer.drain()


@pytest.fixture
def call() -> str:
    """A call id nobody else uses."""
    return f"CA_{uuid4().hex[:12]}"


# An agent's own log is one per name, and every test shares the database: each takes its own name.
@pytest.fixture
def agent() -> str:
    """An agent slug nobody else uses."""
    return f"agent-{secrets.token_hex(4)}"


# A fixed sleep holds on a laptop and loses the race on a loaded runner: wait for the thing.
async def until(happened: Callable[[], bool], within_s: float = 5.0) -> None:
    """Wait for something that happens on its own time; the test fails past within_s."""
    deadline = time.monotonic() + within_s
    while not happened():
        assert time.monotonic() < deadline, "it never happened"
        await asyncio.sleep(0.02)


@asynccontextmanager
async def holding(gateway: Gateway, tenant: Tenant, agent: str) -> AsyncGenerator[ClientConnection]:
    """An app socket holding the agent with the tenant's server key, as an SDK holds it."""
    async with gateway.socket("/v1/apps", tenant.server) as app:
        register = AgentRegister(routes=[]).model_dump(mode="json")
        await app.send(json.dumps({"type": "agent.register", "agent": agent, "call": None, "data": register}))
        await received(app, "agent.registered")
        yield app


# The sandbox fleet's key serves every org of its env: as in production it is filed under an org
# of its own (the box's), never the tenant's, so a worker reaches the tenant's agents only through
# the scope its dispatch names (2026-10-16: a key filed under the tenant hid that it was ignored).
@pytest.fixture
async def fleet(gateway: Gateway, sessions: async_sessionmaker[AsyncSession]) -> AsyncIterator[GatewayClient]:
    """The served gateway as a sandbox worker reaches it, with the fleet's key."""
    the_box = await make_tenant(sessions)
    async with sessions.begin() as session:
        issue = keys.Issue(
            org=the_box.org, env=Env.sandbox, scopes=frozenset({KeyScope.fleet}), label="the suite's fleet"
        )
        _, secret = await keys.issue_key(session, issue)
    client = gateway_at(gateway.url, secret)
    yield client
    await client.aclose()


@pytest.fixture
def acme() -> str:
    """The name of the vendor installed for the whole run, as a test names the vendor it builds on."""
    return fake_acme.ACME
