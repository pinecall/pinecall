"""The calls' loop: the reaper, which seals what nothing runs any more and lets go of what is over."""

import asyncio
import logging
import time

from livekit import api
from sqlalchemy.exc import SQLAlchemyError

from pinecall_runtime.calls.service.reaper import end_parked, let_go, reap
from pinecall_runtime.calls.service.serving import Serving
from pinecall_runtime.exceptions import PinecallError
from pinecall_runtime.postgres import is_cancellation

logger = logging.getLogger(__name__)

REAPED_EVERY_S = 60.0


# A pass that fails is said, and the next one runs: the reaper never stops, a database or an SFU
# that did not answer included.
async def reap_forever(serving: Serving) -> None:
    """A pass now, and one every minute."""
    while True:
        try:
            await reap(serving, time.time())
            end_parked(serving, time.monotonic())
            await let_go(serving, time.monotonic())
        except (PinecallError, api.TwirpError, OSError, SQLAlchemyError) as failed:
            if is_cancellation(failed):
                raise
            logger.warning("the reaper's pass failed; the next is in %.0f s", REAPED_EVERY_S, exc_info=True)
        await asyncio.sleep(REAPED_EVERY_S)
