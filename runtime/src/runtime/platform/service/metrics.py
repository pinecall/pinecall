"""`/metrics`: what each owner says of itself, in Prometheus's text, to the addresses the box trusts alone."""

import ipaddress
from collections.abc import Sequence
from typing import Protocol

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from runtime.exceptions import Forbidden
from runtime.kit.loops import Loops
from runtime.kit.prometheus import family
from runtime.platform.repository.database import DatabaseRepository, ReplicaLag
from runtime.postgres import DatabaseError, pool_measures

NOT_HERE = (
    "/metrics answers the addresses PINECALL_METRICS_FROM names (the box's loopback unless said), "
    "never a forwarded request: curl http://127.0.0.1:8080/metrics from inside"
)
TEXT_FORMAT = "text/plain; version=0.0.4; charset=utf-8"


# One per owner, each saying what it holds: a domain's measures are its own to name, and the route
# reads them all without knowing any (calls-endpoints-2 A).
class Collector(Protocol):
    """What one owner says of itself on `/metrics`."""

    async def collect(self, now: float) -> str:
        """Its families as they stand now, in Prometheus's text."""
        ...


# No key: the address is the fence, and a scraper inside the cluster holds none. A request through
# the load balancer always carries X-Forwarded-For, and is refused whatever it says.
def check_reader(client: str, forwarded: bool, networks: str) -> None:
    """Refuse a reader that is not one of the addresses the box names, or that came through a proxy."""
    if forwarded or not is_from_any(client, networks):
        raise Forbidden(NOT_HERE)


def is_from_any(client: str, networks: str) -> bool:
    """Whether the address is one of the comma-separated addresses or networks."""
    try:
        address = ipaddress.ip_address(client)
    except ValueError:
        return False
    named = (part.strip() for part in networks.split(",") if part.strip())
    return any(address in ipaddress.ip_network(network, strict=False) for network in named)


async def read_metrics(collectors: Sequence[Collector], now: float) -> str:
    """Every owner's families, in the order the process lists its owners."""
    return "".join([await collector.collect(now) for collector in collectors])


class ProcessMetrics:
    """The process's own: its pool of connections, its loops, and how far the database's standbys lag."""

    def __init__(self, engine: AsyncEngine, sessions: async_sessionmaker[AsyncSession], loops: Loops) -> None:
        """What it reads."""
        self._engine = engine
        self._sessions = sessions
        self._loops = loops

    async def collect(self, now: float) -> str:
        """The pool, every loop's heartbeat, the standbys' lag."""
        del now
        size, checked_out = pool_measures(self._engine)
        beats = self._loops.beats()
        lags = await self._replica_lags()
        return "".join(
            (
                family(
                    "pinecall_pool_connections",
                    "Connections the pool holds open, lent out now, and at most.",
                    "gauge",
                    [({"state": "open"}, size), ({"state": "in_use"}, checked_out), ({"state": "max"}, size)],
                ),
                family(
                    "pinecall_loop_running",
                    "Whether each loop the process must keep (the reaper, the sweep) still runs.",
                    "gauge",
                    [({"loop": beat.name}, int(beat.alive)) for beat in beats],
                ),
                family(
                    "pinecall_loop_last_pass_seconds",
                    "How long ago each loop's last pass ended.",
                    "gauge",
                    [({"loop": beat.name}, beat.last_pass_s) for beat in beats if beat.last_pass_s is not None],
                ),
                family(
                    "pinecall_loop_failures_total",
                    "Passes of each loop that failed since the process started.",
                    "counter",
                    [({"loop": beat.name}, beat.failures) for beat in beats],
                ),
                family(
                    "pinecall_replication_lag_seconds",
                    "How far behind each standby is in replaying the primary's WAL.",
                    "gauge",
                    [({"replica": lag.replica}, lag.lag_s) for lag in lags],
                ),
            )
        )

    # A database that cannot say leaves the family empty: the scrape still answers.
    async def _replica_lags(self) -> list[ReplicaLag]:
        try:
            async with self._sessions() as session:
                return await DatabaseRepository(session).list_replica_lags()
        except DatabaseError:
            return []
