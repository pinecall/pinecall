"""The live side's parts: one of each thing a call served here reaches, built once and handed to its use cases."""

from dataclasses import dataclass
from datetime import UTC, datetime

import httpx
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from runtime.alerts import service as alerts
from runtime.calls import service as calls
from runtime.calls.log import Feeds, Logs, Store
from runtime.config import Settings
from runtime.fleet import service as fleet
from runtime.kit.crypto import Vault
from runtime.live.holders import Holders
from runtime.live.peers import Owners
from runtime.live.served import Calls
from runtime.live.sockets import Sockets
from runtime.livekit import Servers
from runtime.providers import service as providers
from runtime.signal import Signal


# The one value of the package that carries collaborators together (G-1): the end of a call needs nine
# of them, and with nine parameters a signature says nothing. It never leaves this domain: no facade
# exports it, no other domain is handed it, and a use case that needs two or three of these takes
# them by name.
@dataclass(frozen=True, slots=True)
class LiveParts:
    """What serves a call on this gateway: the process's connections, the logs, and the live side's own objects."""

    settings: Settings
    vault: Vault
    http: httpx.AsyncClient
    servers: Servers
    signal: Signal
    sessions: async_sessionmaker[AsyncSession]
    store: Store
    logs: Logs
    feeds: Feeds
    prompts: calls.Prompts
    sockets: Sockets
    holders: Holders
    owners: Owners
    calls: Calls
    # The dispatcher that sends a call into a room.
    offering: fleet.Offering
    alerting: alerts.Alerting
    health: providers.VendorHealth
    spending: alerts.UnusualSpend

    @property
    def now(self) -> datetime:
        """This moment by the store's clock, the one every entry of a call is stamped with."""
        return datetime.fromtimestamp(self.store.clock(), UTC)
