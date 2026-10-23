"""The calls' loop: the reaper, which seals what nothing runs any more and lets go of what is over."""

import asyncio
import time

from pinecall_runtime.calls.service.binding import hand_parked
from pinecall_runtime.calls.service.reaper import end_parked, let_go, reap
from pinecall_runtime.calls.service.serving import Serving
from pinecall_runtime.kit.loops import survived

REAPED_EVERY_S = 60.0


# Every part of a pass stands alone, whatever it raises: a call the reaper cannot seal (a log it
# cannot read, a database or an SFU that did not answer) never keeps the others from being let go,
# and never stops the loop. The loop once caught four classes of error, and a pydantic one out of a
# log it could not read ended it for good: the calls another gateway sealed kept their seats until a
# restart (2026-10-23 eval, K F5).
async def reap_forever(serving: Serving) -> None:
    """A pass now, and one every minute."""
    while True:
        with survived("the reaper's sealing of the quiet calls"):
            await reap(serving, time.time())
        with survived("the reaper's handing on of the parked calls"):
            await hand_parked(serving.live, serving.registry)
        with survived("the reaper's ending of the parked calls"):
            end_parked(serving, time.monotonic())
        with survived("the reaper's letting go of the calls that are over"):
            await let_go(serving, time.monotonic())
        await asyncio.sleep(REAPED_EVERY_S)
