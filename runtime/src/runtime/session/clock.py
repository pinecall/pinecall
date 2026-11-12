"""A call's time: its ceiling, warned before it ends, a chat in a room ended when quiet, the idle lines."""

import asyncio
import time
from collections.abc import Awaitable, Callable

from runtime.agents.declaration import Idle
from runtime.kit.loops import survive
from runtime.session.session import Session
from runtime.wire.events import CreditsExhausted

# A limit under two minutes is told at its half instead.
WARNED_BEFORE_S = 60
CLOSING = (
    "The call reaches its time limit in about a minute. Bring it to a close now: answer what is "
    "pending in a sentence, tell the caller the call has to end soon, and say goodbye."
)
# How often a call looks at whether its line has gone quiet.
LOOK_EVERY_S = 0.25

# How the clock waits: asyncio's, or one a test hands in to pass its time at once.
type Sleep = Callable[[float], Awaitable[None]]


# The limit holds while somebody else has the line; only the warning is skipped, since a
# generated turn would talk over them.
async def keep_time(
    session: Session, limit_s: int, *, exhausted: CreditsExhausted | None, sleep: Sleep = asyncio.sleep
) -> None:
    """Warn the agent before the limit and end the call at it; nothing when there is none."""
    if limit_s == 0:
        return
    warned_at = limit_s - WARNED_BEFORE_S if limit_s >= 2 * WARNED_BEFORE_S else limit_s / 2
    await sleep(warned_at)
    # A warning that cannot be given is said, and the limit still holds: the timer that ended on it
    # would leave the call with no ceiling.
    with survive("warning the agent that its time is nearly up", session.call.context.call):
        if session.line.agent_may_speak:
            session.live.generate_reply(instructions=CLOSING)
    await sleep(limit_s - warned_at)
    if exhausted is not None:
        with survive("saying the credits are exhausted", session.call.context.call):
            await session.call.writing.write("credits.exhausted", exhausted)
    session.hang_up("timeout", "platform")


# A chat in a room has no ceiling, and a visitor who leaves the page open would hold its place for
# ever (one did for over an hour on 2026-10-03): it ends once the person has said nothing for long.
async def end_when_quiet(session: Session, quiet_s: float, *, sleep: Sleep = asyncio.sleep) -> None:
    """End the call once the person has said nothing for `quiet_s`; nothing when zero."""
    if quiet_s == 0:
        return
    while True:
        left = quiet_s - (time.monotonic() - session.last_heard)
        if left <= 0:
            session.hang_up("timeout", "platform")
            return
        await sleep(left)


# A tool running, a reply being written, the hold, a person on the line: the caller is not the one keeping quiet.
def _is_waiting_for_the_caller(session: Session) -> bool:
    live = session.live
    return live.agent_state == "listening" and live.user_state != "speaking" and session.line.agent_may_speak


# Only the time the agent is waiting on the caller counts, so an idle line's own length is not silence;
# whatever the caller says starts both counts over.
async def watch_the_quiet(
    session: Session, idle: Idle | None, silence_s: int | None, *, sleep: Sleep = asyncio.sleep
) -> None:
    """Say the idle lines while the caller is quiet, and end the call at its silence timeout; neither set, nothing."""
    if idle is None and silence_s is None:
        return
    heard = session.last_heard
    said = 0
    since_line = 0.0
    quiet = 0.0
    while True:
        await sleep(LOOK_EVERY_S)
        if session.last_heard != heard:
            heard, said, since_line, quiet = session.last_heard, 0, 0.0, 0.0
        if not _is_waiting_for_the_caller(session):
            since_line = 0.0
            continue
        since_line += LOOK_EVERY_S
        quiet += LOOK_EVERY_S
        if silence_s is not None and quiet >= silence_s:
            session.hang_up("timeout", "platform")
            return
        if idle is not None and said < idle.times and since_line >= idle.after_s:
            with survive("saying an idle line", session.call.context.call):
                session.live.say(idle.says[said % len(idle.says)], allow_interruptions=True)
            said += 1
            since_line = 0.0
