"""A spoken simulation with no slot free waits for the fleet to grow, saying `fleet.full` on the agent's log once."""

import time
from collections.abc import Awaitable, Callable

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from runtime.calls.log import Logs
from runtime.enums import Channel, Env
from runtime.exceptions import ServiceUnavailable
from runtime.fleet import service as fleet
from runtime.kit.retry import until
from runtime.wire.events import FleetFull

# A simulation the console or the CLI starts waits for a slot instead of being refused: the fleet grows
# on the calls already on it (a scaled worker's node takes a minute or two), and ten placed together on
# a sandbox of two slots were refused eight times before the node came (2026-11-04).
WAITED_S = 180.0
ASKED_EVERY_S = 2.0
NO_SEAT_IN_TIME = "every seat of the {env}'s fleet held a call for {waited:.0f} s: the simulation did not start"


async def wait_for_fleet_slot(
    sessions: async_sessionmaker[AsyncSession],
    offering: fleet.Offering,
    roster: fleet.Roster,
    logs: Logs,
    env: Env,
    agent: str,
    the_fleet: str,
) -> float:
    """Wait for a slot of the fleet, saying `fleet.full` on the agent's log once; the seconds waited."""

    async def asks() -> bool:
        return await offering.has_a_slot(the_fleet)

    async def full() -> None:
        async with sessions.begin() as session:
            totals = await fleet.totals_of(session, roster, the_fleet, time.time())
        said = FleetFull(channel=Channel.web, workers=totals.workers, active=totals.active)
        await logs.agent(agent).append("fleet.full", said.dump())

    return await wait_for_slot(asks, full, env=env)


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
        waited = time.monotonic() - began
        raise ServiceUnavailable(NO_SEAT_IN_TIME.format(env=env.value, waited=waited))
    return time.monotonic() - began
