"""The live side's loops: the reaper, the adopting of an orphaned call, and the reading of the mailboxes."""

import logging
import time

from runtime.kit.loops import loop, survive
from runtime.live.parts import LiveParts
from runtime.live.service import handoff, inboxes, reaper
from runtime.live.service.whatsapp import Threads

logger = logging.getLogger(__name__)

REAPED_EVERY_S = 60.0
ADOPTED_EVERY_S = 1.0
# An email is answered within a pass or two: nobody expects a reply by email in seconds.
READ_EVERY_S = 20.0


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


@loop("inboxes", every_s=READ_EVERY_S)
async def read_inboxes(live: LiveParts, threads: Threads) -> None:
    """One pass: the mailboxes this gateway reads, read, and each new email heard on its thread."""
    await inboxes.read_inboxes(live, threads)
