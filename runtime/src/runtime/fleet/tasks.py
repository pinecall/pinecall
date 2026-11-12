"""The fleet's loops: the sweep that offers a room again, and the tick that finds silent workers."""

import time

from runtime.fleet.service import slots
from runtime.fleet.service.offers import Offering
from runtime.fleet.service.roster import Roster
from runtime.kit.loops import loop

SWEPT_EVERY_S = 3.0


# A pass that fails is said, and the next one runs: the sweep never stops, whatever it raises (it
# once caught four classes of error, and any other ended it for good). A room it cannot offer
# again is said by the sweep itself, and the rooms behind it are offered all the same.
@loop("offers", every_s=SWEPT_EVERY_S)
async def sweep_offers(offering: Offering) -> None:
    """Offer again every room nobody opened in time, on any gateway."""
    await offering.sweep()


# A worker that stops beating sends nothing to say so: its silence is found on this tick.
@loop("roster", every_s=slots.HEARTBEAT_S)
async def watch_roster(roster: Roster) -> None:
    """Say which workers this gateway heard and has not for too long, and forget the ones long gone."""
    roster.forget_silent(time.time())
