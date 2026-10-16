"""The fleet's loops: the sweep that offers a room again, and the tick that finds silent workers."""

import asyncio
import logging
import time

from livekit import api
from sqlalchemy.exc import SQLAlchemyError

from pinecall_runtime.exceptions import PinecallError
from pinecall_runtime.fleet.service.offers import Offering
from pinecall_runtime.fleet.service.roster import HEARTBEAT_S, Roster
from pinecall_runtime.postgres import is_cancellation

logger = logging.getLogger(__name__)

SWEPT_EVERY_S = 3.0


# A pass that fails is said, and the next one runs: the sweep never stops, a database or an SFU
# that did not answer included.
async def sweep_offers(offering: Offering) -> None:
    """Every few seconds, offer again every room nobody opened in time, on any gateway."""
    while True:
        try:
            await offering.sweep()
        except (PinecallError, api.TwirpError, OSError, SQLAlchemyError) as failed:
            if is_cancellation(failed):
                raise
            logger.warning("the offers' sweep failed; the next is in %.0f s", SWEPT_EVERY_S, exc_info=True)
        await asyncio.sleep(SWEPT_EVERY_S)


# A worker that stops beating sends nothing to say so: its silence is found on this tick.
async def watch_roster(roster: Roster) -> None:
    """Once a heartbeat, say which workers this gateway heard and has not for too long."""
    while True:
        await asyncio.sleep(HEARTBEAT_S)
        roster.forget_silent(time.time())
