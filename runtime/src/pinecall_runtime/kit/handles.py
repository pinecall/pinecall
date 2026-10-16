"""The process-wide handles the lifespan builds once: settings, the vault, HTTP, LiveKit, the signal."""

from dataclasses import dataclass
from typing import Annotated

import httpx
from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from pinecall_runtime.config import Settings
from pinecall_runtime.kit.crypto import Vault
from pinecall_runtime.livekit import Servers
from pinecall_runtime.redis import Signal


@dataclass(frozen=True, slots=True)
class Handles:
    """What every service that reaches outside Postgres is handed: one of each, for the process."""

    settings: Settings
    vault: Vault
    http: httpx.AsyncClient
    servers: Servers
    signal: Signal
    sessions: async_sessionmaker[AsyncSession]


def handles_of(request: Request) -> Handles:
    """The handles the lifespan put on the app."""
    handles: Handles = request.app.state.handles
    return handles


TheHandles = Annotated[Handles, Depends(handles_of)]
