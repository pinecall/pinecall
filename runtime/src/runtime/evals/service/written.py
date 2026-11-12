"""The written line: a persona conversing on a written call, and a golden played on one turn by turn."""

import asyncio
import time
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from types import TracebackType
from typing import Self

from livekit.agents import APIError

from runtime.calls.log import Logs, Store, Subscription
from runtime.evals.service import turns
from runtime.evals.service.hearing import Said
from runtime.evals.service.turn_checks import TurnRun
from runtime.exceptions import PinecallError
from runtime.kit.text import JsonObject
from runtime.providers import service as providers
from runtime.session import service as session
from runtime.wire.base import Command
from runtime.wire.goldens import Golden
from runtime.wire.metrics import ModelUsage
from runtime.wire.parts import EndedBy, EndReason

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
EVENT_SAID_BY_THE_CLASS = "The agent declares the event the turn sends."
CALL_EVENT = "call.event"


# The written caller takes its turns as the spoken one does (the first line after the agent's
# opening, each next once the agent's whole answer is in, read off the same log) and hangs up
# last, so the call is sealed and judged like any other.
class WrittenLine:
    """A written call as its simulated caller is on it: the gateway's own session of it, heard and ended."""

    def __init__(self, running: session.Session, logs: Logs, store: Store) -> None:
        self._running = running
        self._logs = logs
        self._store = store
        # When the caller began its last line: the agent hears a written one the moment it is said.
        self._said_at = store.clock()

    async def __aenter__(self) -> Self:
        """Start the call."""
        await self._running.start()
        self._said_at = self._store.clock()
        return self

    # A line that broke on our side ends the call it opened: left open, it holds the org's line.
    async def __aexit__(
        self, kind: type[BaseException] | None, error: BaseException | None, trace: TracebackType | None
    ) -> None:
        """End the call as broken when the conversation broke on it."""
        if isinstance(error, PinecallError):
            await session.end(self._running, *BROKE)

    async def say(self, text: str) -> ModelUsage | None:
        """Say one line into the call, unless it is over; a written line has no voice to pay for."""
        self._said_at = self._store.clock()
        if not self._running.closed:
            await session.hear(self._running, text)
        return None

    async def wait_for_answer(self, lines: int, landed: turns.Landed) -> bool:
        """Wait until the agent answered this many lines; False on a call that is over."""
        if self._running.closed:
            return False
        call = self._running.call.context.call
        return await turns.wait_for_answer(self._logs, self._store, call, lines, since=self._said_at, landed=landed)

    async def hang_up(self) -> None:
        """Hang up, unless the agent or a person ended the call first."""
        if not self._running.closed:
            await session.end(self._running, *HUNG_UP)

    def list_said(self) -> Sequence[Said]:
        """Nothing: the agent reads a written line as it was written."""
        return ()


@dataclass(frozen=True, slots=True)
class Unplayed:
    """Why the turn that broke was never played: the score it reads as, and what it was held to."""

    metric: str
    reason: str
    criteria: str


# One line just run: its number from 1 and livekit's run of it. True when the turn held.
type JudgeTurn = Callable[[int, TurnRun], Awaitable[bool]]


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


# A golden on a written call is another mechanism, not another line: each turn is livekit's test run,
# judged as it ends. The call opens with no greeting (a run starts mid-conversation); the facts go
# through the app's own `call.event`, so an event the agent never declared is refused as on a real call.
async def drive(
    running: session.Session,
    golden: Golden,
    heard: Subscription,
    judge: JudgeTurn,
    *,
    is_held: Callable[[], bool],
) -> Played:
    """Start the call, play each turn and judge it, stop at the first that broke, then hang up."""
    await running.start()
    try:
        kept_on, broke_at, unplayed = await _play_turns(running, golden, heard, judge, is_held)
    except Exception:
        # Whatever broke the run, the call it opened ends: left open, it holds the org's line.
        await session.end(running, *BROKE)
        raise
    # An agent that ended the call already wrote why: hanging up again would overwrite it.
    if running.ended is None:
        await session.end(running, *(BROKE if unplayed else HUNG_UP if kept_on else APP_DETACHED))
    else:
        await running.close()
    return Played(held=kept_on, requests=tuple(running.call.requests), broke_at=broke_at, unplayed=unplayed)


async def wait_until_quiet(heard: Subscription, *, quiet_s: float = QUIET_S) -> None:
    """Return once nothing reached the log for `quiet_s`, and always within AT_MOST_S."""
    loop = asyncio.get_running_loop()
    deadline = loop.time() + AT_MOST_S
    while (left := deadline - loop.time()) > 0:
        try:
            await asyncio.wait_for(anext(heard), min(quiet_s, left))
        except (TimeoutError, StopAsyncIteration):
            return


# A line is livekit's test run; a fact is the app's call.event, and the log going quiet after it
# is the only sign the app is done. A call the agent ended plays no further turn.
async def _play_turns(
    running: session.Session, golden: Golden, heard: Subscription, judge: JudgeTurn, is_held: Callable[[], bool]
) -> tuple[bool, int | None, Unplayed | None]:
    await wait_until_quiet(heard)
    context = running.call.context
    for number, turn in enumerate(golden.turns, 1):
        if not is_held():
            return False, None, None
        if turn.event is not None:
            sent = {"name": turn.event.name, "data": dict(turn.event.data)}
            command = Command(type=CALL_EVENT, agent=context.route.agent, call=context.call, data=sent)
            refused = await session.take(running, command)
            await wait_until_quiet(heard)
            if refused is not None:
                reason = EVENT_REFUSED.format(number=number, error=refused.message)
                return True, number, Unplayed(f"t{number}.event", reason, EVENT_SAID_BY_THE_CLASS)
            continue
        began = time.time()
        try:
            run = await session.run(running, turn.say or "")
        except APIError as failed:
            await wait_until_quiet(heard)
            reason = VENDOR_FAILED.format(number=number, error=providers.sentence_of(failed))
            return True, number, Unplayed(f"t{number}.model", reason, MODEL_ANSWERS)
        await wait_until_quiet(heard)
        ended_by = None if running.ended is None else running.ended[1]
        if not await judge(number, TurnRun(run, began, ended_by)):
            return True, number, None
        if ended_by is not None:
            break
    return True, None, None
