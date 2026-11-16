"""The live side's loops: the reaper, the adopting of an orphaned call, and the handing on of one its worker left."""

import asyncio
import logging
import time

from runtime.kit.loops import loop, survive
from runtime.live.parts import LiveParts
from runtime.live.service import handoff, reaper, stranded

logger = logging.getLogger(__name__)

REAPED_EVERY_S = 60.0
ADOPTED_EVERY_S = 1.0
CUT_LOOKED_AT_EVERY_S = 0.5


# Every part of a pass stands alone, whatever it raises: a call the reaper cannot end (a log it
# cannot read, a database or an SFU that did not answer) never keeps the others from being let go,
# and never stops the loop. The loop once caught four classes of error, and a pydantic one out of a
# log it could not read ended it for good: the calls another gateway sealed went on counting against their orgs until a
# restart (2026-10-23 eval, K F5).
@loop("reaper", every_s=REAPED_EVERY_S)
async def reap(live: LiveParts) -> None:
    """One pass: the quiet calls ended, the parked ones handed on or ended, the ones that are over let go."""
    with survive("the reaper's sealing of the quiet calls"):
        await reaper.reap(live, time.time())
    with survive("the reaper's handing on of the parked calls"):
        await handoff.hand_parked(live.calls, live.holders)
    with survive("the reaper's ending of the parked calls"):
        reaper.end_parked(live, time.monotonic())
    with survive("the reaper's letting go of the calls that are over"):
        await reaper.let_go(live, time.monotonic())


@loop("adoption", every_s=ADOPTED_EVERY_S)
async def adopt(live: LiveParts) -> None:
    """One pass: the calls whose opener is gone and whose worker reads its commands here are this gateway's."""
    for call in await handoff.adopt_orphans(live.calls, live.holders, time.monotonic()):
        logger.warning("adopted %s: the gateway that opened it is gone, and its worker reads here", call)


# Each call stands alone: one that cannot be handed on (a LiveKit that did not answer) is said, and
# LiveKit's own word of the lost agent offers it later (`stranded.offer_stranded`). A gateway told to
# stop ends every stream itself, and its workers open them again on another: it hands nothing on.
@loop("stranded", every_s=CUT_LOOKED_AT_EVERY_S)
async def hand_on(live: LiveParts, closing: asyncio.Event) -> None:
    """One pass: the spoken calls whose worker stopped reading its commands are handed to another worker."""
    if closing.is_set():
        return
    for served in live.calls.take_cut(time.monotonic(), stranded.GONE_AFTER_S):
        with survive("handing on a call whose worker went silent", served.call):
            await stranded.hand_on_cut(live, served)
