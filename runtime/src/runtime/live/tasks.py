"""The live side's loop: the reaper, which ends what nothing runs any more and lets go of what is over."""

import time

from runtime.kit.loops import loop, survive
from runtime.live.parts import LiveParts
from runtime.live.service import handoff, reaper

REAPED_EVERY_S = 60.0


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
