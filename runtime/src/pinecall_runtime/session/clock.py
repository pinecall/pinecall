"""A call's time: its ceiling, warned before it ends, and a chat in a room ended when quiet."""

import asyncio
import time

from pinecall_runtime.agents.declaration import Idle
from pinecall_runtime.kit.loops import survived
from pinecall_runtime.session.session import Session
from pinecall_runtime.wire.events import CreditsExhausted

# A limit under two minutes is told at its half instead.
WARNED_BEFORE_S = 60
CLOSING = (
    "The call reaches its time limit in about a minute. Bring it to a close now: answer what is "
    "pending in a sentence, tell the caller the call has to end soon, and say goodbye."
)
# How often a call looks at whether its line has gone quiet.
LOOK_EVERY_S = 0.25


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


def _waiting_for_the_caller(session: Session) -> bool:
    # A tool running, a reply being written, the hold, a person on the line: the caller is not the one keeping quiet.
    return (
        session.live.agent_state == "listening"
        and session.live.user_state != "speaking"
        and not session.on_hold
        and not session.call.a_person_has_the_line
        and not session.call.waiting_for_a_person
    )


# Only the time the agent is waiting on the caller counts, so an idle line's own length is not silence;
# whatever the caller says starts both counts over.
async def watch_the_quiet(session: Session, idle: Idle | None, silence_s: int | None) -> None:
    """Say the idle lines while the caller is quiet, and end the call at its silence timeout; neither set, nothing."""
    if idle is None and silence_s is None:
        return
    heard = session.last_heard
    said = 0
    since_line = 0.0
    quiet = 0.0
    while True:
        await asyncio.sleep(LOOK_EVERY_S)
        if session.last_heard != heard:
            heard, said, since_line, quiet = session.last_heard, 0, 0.0, 0.0
        if not _waiting_for_the_caller(session):
            since_line = 0.0
            continue
        since_line += LOOK_EVERY_S
        quiet += LOOK_EVERY_S
        if silence_s is not None and quiet >= silence_s:
            session.hang_up("timeout", "platform")
            return
        if idle is not None and said < idle.times and since_line >= idle.after_s:
            with survived("saying an idle line", session.call.context.call):
                session.live.say(idle.says[said % len(idle.says)], allow_interruptions=True)
            said += 1
            since_line = 0.0
