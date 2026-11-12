"""The live side's loops: the reaper, which ends what nothing runs any more, and the adopting of an orphaned call."""

import logging
import time

from runtime.kit.loops import loop, survive
from runtime.live.parts import LiveParts
from runtime.live.service import handoff, reaper

logger = logging.getLogger(__name__)

REAPED_EVERY_S = 60.0
ADOPTED_EVERY_S = 1.0


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
