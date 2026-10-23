"""The fleet's loops: the sweep that offers a room again, and the tick that finds silent workers."""

import asyncio
import time

from pinecall_runtime.fleet.service.offers import Offering
from pinecall_runtime.fleet.service.roster import HEARTBEAT_S, Roster
from pinecall_runtime.kit.loops import survived

SWEPT_EVERY_S = 3.0


# A pass that fails is said, and the next one runs: the sweep never stops, whatever it raises (it
# once caught four classes of error, and any other ended it for good). A room it cannot offer
# again is said by the sweep itself, and the rooms behind it are offered all the same.
async def sweep_offers(offering: Offering) -> None:
    """Every few seconds, offer again every room nobody opened in time, on any gateway."""
    while True:
        with survived("the offers' sweep"):
            await offering.sweep()
        await asyncio.sleep(SWEPT_EVERY_S)


# A worker that stops beating sends nothing to say so: its silence is found on this tick.
async def watch_roster(roster: Roster) -> None:
    """Once a heartbeat, say which workers this gateway heard and has not for too long."""
    while True:
        await asyncio.sleep(HEARTBEAT_S)
        with survived("the roster's look for silent workers"):
            roster.forget_silent(time.time())
