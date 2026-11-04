"""A spoken simulation with no seat free waits for the fleet to grow, saying `fleet.full` on the agent's log once."""

import asyncio
import time
from collections.abc import Awaitable, Callable

from pinecall_runtime.calls import service as calls
from pinecall_runtime.enums import Channel, Env
from pinecall_runtime.exceptions import ServiceUnavailable
from pinecall_runtime.kit.auth import Scope
from pinecall_runtime.wire.events import FleetFull

# A simulation the console or the CLI starts waits for a seat instead: the fleet grows on the calls
# already on it (a scaled worker's node takes a minute or two), and ten placed together on a
# sandbox of two seats were refused eight times before the node came (2026-11-04).
SEAT_WAITED_S = 180.0
SEAT_ASKED_EVERY_S = 2.0
NO_SEAT_IN_TIME = "every seat of the {env}'s fleet held a call for {waited:.0f} s: the simulation did not start"


async def seat_waited_for(serving: calls.Serving, scope: Scope, agent: str, the_fleet: str) -> float:
    """Wait for a seat of the fleet, saying `fleet.full` on the agent's log once; the seconds waited."""

    async def asks() -> bool:
        return await serving.offering.has_a_seat(the_fleet)

    async def full() -> None:
        totals = serving.roster.totals_of(the_fleet, time.time())
        said = FleetFull(channel=Channel.web, workers=totals.workers, active=totals.active)
        await serving.logs.agent(agent).append("fleet.full", said.dump())

    return await wait_for_a_seat(asks, full, env=scope.env)


async def wait_for_a_seat(
    asks: Callable[[], Awaitable[bool]],
    full: Callable[[], Awaitable[None]],
    *,
    env: Env,
    within_s: float = SEAT_WAITED_S,
    every_s: float = SEAT_ASKED_EVERY_S,
) -> float:
    """Ask for a seat every few seconds until one is there; `full` is told once, on the first miss."""
    began = time.monotonic()
    told = False
    while not await asks():
        if not told:
            await full()
            told = True
        waited = time.monotonic() - began
        if waited >= within_s:
            raise ServiceUnavailable(NO_SEAT_IN_TIME.format(env=env.value, waited=waited))
        await asyncio.sleep(every_s)
    return time.monotonic() - began
