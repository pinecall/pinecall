"""A worker's entries on its call's log: each one checked, the batch written, and the append counted."""

import time
from collections.abc import Sequence

from runtime.actor import Actor
from runtime.alerts import service as alerts
from runtime.exceptions import Forbidden, ValidationError
from runtime.kit.prometheus import Histogram
from runtime.kit.text import JsonObject
from runtime.live.parts import LiveParts
from runtime.live.served import Calls, Served
from runtime.live.service import openings
from runtime.providers import service as providers
from runtime.wire.base import BatchedEntry, Entry
from runtime.wire.events import EVENTS, GATEWAY_WRITES

# Seconds: an append waits on one Postgres transaction, so the buckets are a transaction's.
APPEND_BOUNDS_S = (0.001, 0.0025, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0)
ERROR = "error"

# The gateway itself reads these two back to end a call and to hand it on, so a worker's that does
# not parse is refused where it is sent, naming the field: a call whose start the seal cannot read
# could never be sealed (2026-10-23: a call.started with no `caller` was taken, and its seal
# answered 500 for ever, the call counting against its org all the while).
LIFECYCLE = ("call.started", "call.ended")


# Called on the append path: a bisect and two additions, no lock (one event loop).
class Appends:
    """What a gateway counted of the appends since it started: how long each took, and how many entries."""

    def __init__(self) -> None:
        """Nothing counted yet."""
        self.seconds = Histogram(APPEND_BOUNDS_S)
        self.entries = 0

    def count(self, seconds: float, entries: int) -> None:
        """One append at the endpoint: how long it took and how many entries it wrote."""
        self.seconds.observe(seconds)
        self.entries += entries


def check_kind(kind: str) -> None:
    """Refuse a type the protocol lacks, or one the gateway alone writes on a log."""
    if kind not in EVENTS:
        raise ValidationError(f"no event is called {kind!r}: the log takes the protocol's own words")
    if kind in GATEWAY_WRITES:
        raise Forbidden(f"{kind!r} is written by the gateway itself, never sent to it")


def check_entry(kind: str, data: JsonObject) -> None:
    """Refuse an entry the log does not take: its type, or the shape of a lifecycle entry."""
    check_kind(kind)
    if kind in LIFECYCLE:
        EVENTS[kind].parse(data, kind)


# A socket has no request to borrow a session from: the call is found on one of its own, given back
# before the first batch is read, so a worker's socket holds no connection for the call's life.
async def get_written_call(live: LiveParts, actor: Actor, call: str) -> Served:
    """The call a worker's socket of batches writes, served here, as its opener's key may reach it."""
    async with live.sessions.begin() as session:
        return await openings.get_served(session, live, actor, call)


# The one rule of an append: each entry checked, the write timed, what it says counted. Until 2026-11
# three endpoint bodies each held it. Taken whole or refused whole; the answer to a retry of the last
# batch is the seqs it was given.
async def append_entries(
    calls: Calls,
    served: Served,
    appends: Appends,
    health: providers.VendorHealth,
    entries: Sequence[BatchedEntry],
    *,
    after: int,
) -> list[Entry]:
    """Write a worker's batch of a call this gateway serves, once and in order."""
    for item in entries:
        check_entry(item.type, item.data)
    # A worker's socket holds its call for as long as it writes: a copy served here stays while it does.
    calls.touch(served.call, time.monotonic())
    began = time.perf_counter()
    written = await served.log.append_many(entries, after=after)
    count_append(appends, health, time.perf_counter() - began, written)
    return written


# The entry comes back with its seq: only the gateway numbers a log.
async def append_entry(
    served: Served,
    appends: Appends,
    health: providers.VendorHealth,
    kind: str,
    data: JsonObject,
    *,
    ephemeral: bool | None = None,
) -> Entry:
    """Write one entry of a call this gateway serves."""
    check_entry(kind, data)
    began = time.perf_counter()
    entry = await served.log.append(kind, data, ephemeral=ephemeral)
    count_append(appends, health, time.perf_counter() - began, [entry])
    return entry


# What /metrics reads: the append's time at the endpoint, and each vendor's failures as they
# come in. A vendor fails a call when an error names its plugin, or when a stage switches away:
# read as the alert of a sealed call reads the same two entries (`alerts.vendor_of`).
def count_append(appends: Appends, health: providers.VendorHealth, seconds: float, entries: Sequence[Entry]) -> None:
    """Count an append's time and entries, and what they say of vendors, for /metrics."""
    appends.count(seconds, len(entries))
    at = time.monotonic()
    for entry in entries:
        vendor = alerts.vendor_of(entry)
        if vendor is None:
            continue
        if entry.type == ERROR:
            code = entry.data.get("code")
            health.count_error(code if isinstance(code, str) else "", vendor)
        if vendor and entry.call is not None:
            health.count_failure(vendor, entry.call, at)
