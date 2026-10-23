"""A call's time: its ceiling, warned before it ends, and a chat in a room ended when quiet."""

import asyncio
import time

from pinecall_runtime.kit.loops import survived
from pinecall_runtime.session.session import Session
from pinecall_runtime.wire.events import CreditsExhausted

# A limit under two minutes is told at its half instead.
WARNED_BEFORE_S = 60
CLOSING = (
    "The call reaches its time limit in about a minute. Bring it to a close now: answer what is "
    "pending in a sentence, tell the caller the call has to end soon, and say goodbye."
)


# The limit holds while a supervisor has the line; only the warning is skipped, since a
# generated turn would talk over them.
async def keep_time(session: Session, limit_s: int, *, exhausted: CreditsExhausted | None) -> None:
    """Warn the agent before the limit and end the call at it; nothing when there is none."""
    if limit_s == 0:
        return
    warned_at = limit_s - WARNED_BEFORE_S if limit_s >= 2 * WARNED_BEFORE_S else limit_s / 2
    await asyncio.sleep(warned_at)
    # A warning that cannot be given is said, and the limit still holds: the timer that ended on it
    # would leave the call with no ceiling.
    with survived("warning the agent that its time is nearly up", session.call.context.call):
        if not session.call.a_person_has_the_line:
            session.live.generate_reply(instructions=CLOSING)
    await asyncio.sleep(limit_s - warned_at)
    if exhausted is not None:
        with survived("saying the credits are exhausted", session.call.context.call):
            await session.call.writing.write("credits.exhausted", exhausted)
    session.hang_up("timeout", "platform")


# A chat in a room has no ceiling, and a visitor who leaves the page open would hold its seat for
# ever (one did for over an hour on 2026-10-03): it ends once the person has said nothing for long.
async def end_when_quiet(session: Session, quiet_s: float) -> None:
    """End the call once the person has said nothing for `quiet_s`; nothing when zero."""
    if quiet_s == 0:
        return
    while True:
        left = quiet_s - (time.monotonic() - session.last_heard)
        if left <= 0:
            session.hang_up("timeout", "platform")
            return
        await asyncio.sleep(left)
