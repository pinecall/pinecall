"""A golden played on a written call, turn by turn; a persona conversing on one, line by line."""

import asyncio
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from livekit.agents import APIError

from pinecall_runtime.calls import service as calls
from pinecall_runtime.evals.service.turns import Landed, NextLine, answered, speak_turns
from pinecall_runtime.exceptions import PinecallError, ValidationError
from pinecall_runtime.judging import service as judging
from pinecall_runtime.kit.text import JsonObject
from pinecall_runtime.providers import service as providers
from pinecall_runtime.session import service as session
from pinecall_runtime.wire.commands import CallEvent
from pinecall_runtime.wire.goldens import Golden
from pinecall_runtime.wire.parts import EndedBy, EndReason

# The wire has no "the app is done reacting": the log going quiet is the sign. Long enough for a
# render and its re-render to be one burst, short enough to cost little per turn.
QUIET_S = 0.15
# An app that never answers cannot hold a run up longer than this per step.
AT_MOST_S = 2.0

APP_DETACHED: tuple[EndReason, EndedBy] = ("app_detached", "platform")
HUNG_UP: tuple[EndReason, EndedBy] = ("caller_hung_up", "caller")
# A golden a turn of which could not be played ends the call it opened.
BROKE: tuple[EndReason, EndedBy] = ("error", "platform")
# A turn that could not be played breaks that golden, not the run: the next golden plays on, and
# this one says why. A line the model's vendor failed (an outage past its retries, a content
# filter's refusal), or a fact the agent never declared, refused as on a real call.
VENDOR_FAILED = "the model's vendor failed turn {number}: {error}"
MODEL_ANSWERS = "The model's vendor answers the turn."
EVENT_REFUSED = "the agent refused turn {number}'s event: {error}"
EVENT_DECLARED = "The agent declares the event the turn sends."


@dataclass(frozen=True)
class Unplayed:
    """Why the turn that broke was never played: the score it reads as, and what it was held to."""

    metric: str
    reason: str
    criteria: str


# One line just run: its number from 1 and livekit's run of it. True when the turn held.
type TurnJudged = Callable[[int, judging.TurnRun], Awaitable[bool]]


@dataclass(frozen=True, slots=True)
class Played:
    """A golden played to its end, to the turn that broke, or to where the app let go."""

    held: bool
    # The requests the model was sent, one per request, as they went.
    requests: tuple[JsonObject, ...]
    # The turn that broke, from 1; None when every turn played held.
    broke_at: int | None = None
    # Why the turn that broke was never played, when it was not a step that broke it.
    unplayed: Unplayed | None = None


# The call opens with no greeting (a run starts mid-conversation); the facts go through the
# app's own `call.event`, so an event the agent never declared is refused as on a real call.
async def drive(
    running: session.Session,
    golden: Golden,
    heard: calls.Subscription,
    judged: TurnJudged,
    *,
    is_held: Callable[[], bool],
) -> Played:
    """Start the call, play each turn and judge it, stop at the first that broke, then hang up."""
    await running.start()
    try:
        kept_on, broke_at, unplayed = await _played(running, golden, heard, judged, is_held)
    except Exception:
        # Whatever broke the run, the call it opened ends: left open, it holds the org's line.
        await session.end_text(running, *BROKE)
        raise
    # An agent that ended the call already wrote why: hanging up again would overwrite it.
    if running.ended is None:
        await session.end_text(running, *(BROKE if unplayed else HUNG_UP if kept_on else APP_DETACHED))
    else:
        await running.close()
    return Played(held=kept_on, requests=tuple(running.call.requests), broke_at=broke_at, unplayed=unplayed)


async def settled(heard: calls.Subscription, *, quiet_s: float = QUIET_S) -> None:
    """Return once nothing reached the log for `quiet_s`, and always within AT_MOST_S."""
    loop = asyncio.get_running_loop()
    deadline = loop.time() + AT_MOST_S
    while (left := deadline - loop.time()) > 0:
        try:
            await asyncio.wait_for(anext(heard), min(quiet_s, left))
        except (TimeoutError, StopAsyncIteration):
            return


# The written caller takes its turns as the spoken one does — the first line after the agent's
# opening, each next once the agent's whole answer is in, read off the same log — and hangs up
# last, so the call is sealed and judged like any other.
async def converse(running: session.Session, logs: calls.Logs, next_line: NextLine, turns: int) -> int:
    """Start the call, say each line the caller improvises as the agent answers; the lines said."""
    call = running.call.context.call
    await running.start()
    # When the caller began its last line: the agent hears a written one the moment it is said.
    said_at = logs.store.clock()

    async def say(line: str) -> None:
        nonlocal said_at
        said_at = logs.store.clock()
        if not running.closed:
            await session.hear_text(running, line)

    async def wait(lines: int, landed: Landed) -> bool:
        if running.closed:
            return False
        return await answered(logs, call, lines, since=said_at, landed=landed)

    try:
        lines = await speak_turns(turns, next_line, say, wait)
    except PinecallError:
        await session.end_text(running, *BROKE)
        raise
    if not running.closed:
        await session.end_text(running, *HUNG_UP)
    return lines


# A line is livekit's test run; a fact is the app's call.event, and the log going quiet after it
# is the only sign the app is done. A call the agent ended plays no further turn.
async def _played(
    running: session.Session, golden: Golden, heard: calls.Subscription, judged: TurnJudged, is_held: Callable[[], bool]
) -> tuple[bool, int | None, Unplayed | None]:
    await settled(heard)
    for number, turn in enumerate(golden.turns, 1):
        if not is_held():
            return False, None, None
        if turn.event is not None:
            try:
                await running.apply(CallEvent(name=turn.event.name, data=dict(turn.event.data)))
            except ValidationError as refused:
                await settled(heard)
                reason = EVENT_REFUSED.format(number=number, error=refused)
                return True, number, Unplayed(metric=f"t{number}.event", reason=reason, criteria=EVENT_DECLARED)
            await settled(heard)
            continue
        began = time.time()
        try:
            run = await session.run_text(running, turn.say or "")
        except APIError as failed:
            await settled(heard)
            reason = VENDOR_FAILED.format(number=number, error=providers.words_of(failed))
            return True, number, Unplayed(metric=f"t{number}.model", reason=reason, criteria=MODEL_ANSWERS)
        await settled(heard)
        ended_by = None if running.ended is None else running.ended[1]
        if not await judged(number, judging.TurnRun(run, began, ended_by)):
            return True, number, None
        if ended_by is not None:
            break
    return True, None, None
