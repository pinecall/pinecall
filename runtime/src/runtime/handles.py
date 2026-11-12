"""One process's handles: what the lifespan builds once, and the getter each one is asked for by."""

import asyncio
from dataclasses import dataclass
from typing import Annotated

import httpx
from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker
from starlette.requests import HTTPConnection

from runtime.config import Settings
from runtime.kit import dns
from runtime.kit.crypto import Vault
from runtime.livekit import Servers
from runtime.signal import Signal


# The internet as the process reaches it. A box's is the network and its DNS; the suite hands its gateway
# one where a test serves a business's API under a name of its own.
@dataclass(frozen=True, slots=True)
class Outside:
    """What the process reaches beyond itself: the transport its HTTP client goes out by, and how a name resolves."""

    transport: httpx.AsyncBaseTransport | None = None
    resolve: dns.Resolve = dns.resolve


THE_INTERNET = Outside()


@dataclass(frozen=True, slots=True)
class Handles:
    """One of each, for the process: its settings, its vault, and its connections."""

    settings: Settings
    vault: Vault
    http: httpx.AsyncClient
    servers: Servers
    signal: Signal
    engine: AsyncEngine
    sessions: async_sessionmaker[AsyncSession]
    # How a name a tenant wrote is resolved before the box reaches it.
    resolve: dns.Resolve = dns.resolve


def handles_of(connection: HTTPConnection) -> Handles:
    """The handles the lifespan yielded."""
    handles: Handles = connection.state.handles
    return handles


def settings_of(connection: HTTPConnection) -> Settings:
    """The process's settings."""
    return handles_of(connection).settings


def vault_of(connection: HTTPConnection) -> Vault:
    """The vault every sealed value is sealed and opened with."""
    return handles_of(connection).vault


def http_of(connection: HTTPConnection) -> httpx.AsyncClient:
    """The process's HTTP client."""
    return handles_of(connection).http


def servers_of(connection: HTTPConnection) -> Servers:
    """Each env's LiveKit client."""
    return handles_of(connection).servers


def signal_of(connection: HTTPConnection) -> Signal:
    """The signal the gateways tell each other on."""
    return handles_of(connection).signal


def sessions_of(connection: HTTPConnection) -> async_sessionmaker[AsyncSession]:
    """The maker of the process's database sessions."""
    return handles_of(connection).sessions


# Streams never end on their own: each is told when the process stops (`app.announce_closing`).
def closing_of(connection: HTTPConnection) -> asyncio.Event:
    """What is set when the process is told to stop."""
    closing: asyncio.Event = connection.state.closing
    return closing


TheSettings = Annotated[Settings, Depends(settings_of)]
TheVault = Annotated[Vault, Depends(vault_of)]
TheHttp = Annotated[httpx.AsyncClient, Depends(http_of)]
TheServers = Annotated[Servers, Depends(servers_of)]
TheSignal = Annotated[Signal, Depends(signal_of)]
TheSessions = Annotated[async_sessionmaker[AsyncSession], Depends(sessions_of)]
TheClosing = Annotated[asyncio.Event, Depends(closing_of)]
