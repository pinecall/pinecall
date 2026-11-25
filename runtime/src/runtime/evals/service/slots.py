"""A spoken simulation takes a seat of the fleet, waiting for one when none is free and saying `fleet.full` once."""

import time
from collections.abc import Awaitable, Callable

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from runtime.calls.log import Logs
from runtime.enums import Channel, Env
from runtime.exceptions import ServiceUnavailable
from runtime.fleet import service as fleet
from runtime.kit.retry import until
from runtime.wire.dispatch import Dispatch
from runtime.wire.events import FleetFull

# A simulation the console or the CLI starts waits for a seat instead of being refused: the fleet grows
# on the calls already on it (a scaled worker's node takes a minute or two), and ten placed together on
# a sandbox of two slots were refused eight times before the node came (2026-11-04). On a fleet that
# does not grow the wait is a queue: sixty calls placed on eight seats (2026-11-24) had the last of them
# wait past three minutes, which was the whole wait then, and those never started. A call waits as long
# as a comparison goes on placing its own. The queue is the fleet's, a line shared between the orgs in
# it (`fleet.service.shares`): a caller here only asks, and each ask says it still waits.
WAITED_S = 45 * 60.0
ASKED_EVERY_S = 2.0


class NoSeat(ServiceUnavailable):
    """Every seat of the env's fleet held a call for the whole wait: the simulation did not start."""

    def __init__(self, env: Env, waited_s: float) -> None:
        super().__init__(
            f"every seat of the {env.value}'s fleet held a call for {waited_s:.0f} s: the simulation did not start"
        )


# The seat is asked for and taken in one step (`Offering.take_seat`): a caller that only asked and
# offered its room later shared the answer with every caller that asked at the same moment.
async def take_fleet_seat(
    sessions: async_sessionmaker[AsyncSession],
    offering: fleet.Offering,
    roster: fleet.Roster,
    logs: Logs,
    env: Env,
    the_fleet: str,
    room: str,
    dispatch: Dispatch,
) -> fleet.Seat:
    """Take a seat of the fleet for the room, waiting for one and saying `fleet.full` once; the seat."""
    agent = dispatch.agent or ""
    taken: list[fleet.Seat] = []

    async def asks() -> bool:
        seat = await offering.take_seat(room, the_fleet, dispatch)
        if seat is not None:
            taken.append(seat)
        return seat is not None

    async def full() -> None:
        async with sessions.begin() as session:
            totals = await fleet.totals_of(session, roster, the_fleet, time.time())
        said = FleetFull(channel=Channel.web, workers=totals.workers, active=totals.active)
        await logs.agent(agent).append("fleet.full", said.dump())

    await wait_for_slot(asks, full, env=env)
    return taken[0]


async def wait_for_slot(
    asks: Callable[[], Awaitable[bool]],
    full: Callable[[], Awaitable[None]],
    *,
    env: Env,
    within_s: float = WAITED_S,
    every_s: float = ASKED_EVERY_S,
) -> float:
    """Ask for a slot every few seconds until one is there; `full` is told once, on the first miss."""
    began = time.monotonic()
    if await asks():
        return 0.0
    await full()

    async def probe() -> bool | None:
        return True if await asks() else None

    if await until(probe, every_s=every_s, within_s=within_s) is None:
        raise NoSeat(env, time.monotonic() - began)
    return time.monotonic() - began
