"""Tests for a call's time: its ceiling, the warning before it, a quiet chat in a room ended."""

import asyncio
from collections.abc import Awaitable, Callable

import pytest
from livekit.agents import llm
from livekit.agents.voice.events import ConversationItemAddedEvent

import runtime.session.clock as clock
from runtime.agents.declaration import Idle
from runtime.calls.log.store import Store
from runtime.session.clock import CLOSING
from runtime.session.commands import apply
from runtime.session.session import Session
from runtime.wire.commands import CallHold, CallUnhold, TakeoverVerb
from runtime.wire.events import CreditsExhausted
from tests.conftest import needs_the_database
from tests.session.conftest import NOBODY, Box, a_session, kinds, model_of, supervised


@needs_the_database
async def test_a_limit_under_two_minutes_is_told_at_its_half_and_ends_at_the_limit(
    box: Box, store: Store, call: str
) -> None:
    session = a_session(box, NOBODY, ["Vamos cerrando"])
    await session.start()
    await clock.keep_time(session, 1, exhausted=None)
    await session.close()
    params = model_of(session).requests
    assert CLOSING in str([getattr(item, "text_content", "") for item in params[0].items])
    ended = next(entry for entry in await store.whole_of(call) if entry.type == "call.ended")
    assert (ended.data["reason"], ended.data["ended_by"]) == ("timeout", "platform")


@needs_the_database
async def test_a_person_on_the_line_is_not_talked_over_and_the_limit_still_holds(
    box: Box, store: Store, call: str
) -> None:
    session = a_session(box, NOBODY, ["nunca"])
    await session.start()
    await apply(session, supervised(TakeoverVerb()))
    await clock.keep_time(session, 1, exhausted=None)
    await session.close()
    assert model_of(session).requests == []
    assert "call.ended" in await kinds(store, call)


@needs_the_database
async def test_the_orgs_minutes_ending_the_call_first_are_written_before_it_ends(
    box: Box, store: Store, call: str
) -> None:
    session = a_session(box, NOBODY)
    await session.start()
    spent = CreditsExhausted(org="org_1", quota="minutes", used=30, limit=30, calls=[])
    await clock.keep_time(session, 1, exhausted=spent)
    await session.close()
    written = await kinds(store, call)
    assert written.index("credits.exhausted") < written.index("call.ended")


async def never(seconds: float) -> None:
    """A clock that must not wait at all."""
    raise AssertionError(f"waited {seconds} s")


@needs_the_database
async def test_no_limit_keeps_no_clock(box: Box) -> None:
    session = a_session(box, NOBODY)
    await clock.keep_time(session, 0, exhausted=None, sleep=never)
    await clock.end_when_quiet(session, 0, sleep=never)


@needs_the_database
async def test_the_agent_is_told_a_minute_before_a_limit_of_two_minutes_or_more(box: Box) -> None:
    slept: list[float] = []

    async def counted(delay: float) -> None:
        slept.append(delay)

    session = a_session(box, NOBODY, ["Vamos cerrando"])
    await session.start()
    await clock.keep_time(session, 300, exhausted=None, sleep=counted)
    await session.close()
    assert slept == [240, 60]


# A warning that could not be given (the session had closed under it) ended the timer, and the call it
# watched had no ceiling: the limit is the call's, the warning only a courtesy before it.
@needs_the_database
async def test_a_warning_that_cannot_be_given_is_said_and_the_limit_still_holds(
    box: Box, caplog: pytest.LogCaptureFixture
) -> None:
    session = a_session(box, NOBODY)
    await session.start()
    await session.live.aclose()
    await clock.keep_time(session, 1, exhausted=None)
    assert session.ended == ("timeout", "platform")
    call = session.call.context.call
    assert f"warning the agent that its time is nearly up failed on {call}" in caplog.text
    await session.close()


# A chat in a room has no ceiling: a visitor who leaves the page open would hold the seat for ever.
@needs_the_database
async def test_a_chat_left_quiet_ends_as_a_timeout_and_a_message_keeps_it(box: Box, store: Store, call: str) -> None:
    session = a_session(box, NOBODY)
    await session.start()
    quiet = asyncio.create_task(clock.end_when_quiet(session, 0.3))
    await asyncio.sleep(0.2)
    message = llm.ChatMessage(role="user", content=["hola"])
    session.live.emit("conversation_item_added", ConversationItemAddedEvent(item=message))
    await asyncio.sleep(0.2)
    assert session.ended is None
    await asyncio.sleep(0.2)
    assert session.ended == ("timeout", "platform")
    await quiet
    await session.close()
    ended = next(entry for entry in await store.whole_of(call) if entry.type == "call.ended")
    assert (ended.data["reason"], ended.data["ended_by"]) == ("timeout", "platform")


# ── the quiet ──


type Tick = Callable[[int], Awaitable[None]]


async def _nothing(_tick: int) -> None:
    return None


def ticking(ticks: list[int], at: Tick = _nothing) -> clock.Sleep:
    """A clock whose every look passes at once, and `at` sees which look it is."""

    async def passes(_seconds: float) -> None:
        ticks.append(len(ticks))
        await at(len(ticks))
        await asyncio.sleep(0)

    return passes


def said_by_the_agent(session: Session) -> list[str]:
    """What the agent said, in order."""
    return [item.text_content or "" for item in session.live.history.messages() if item.role == "assistant"]


def heard(session: Session, text: str) -> None:
    """The caller says something, as livekit tells it."""
    message = llm.ChatMessage(role="user", content=[text])
    session.live.emit("conversation_item_added", ConversationItemAddedEvent(item=message))


@needs_the_database
async def test_idle_lines_are_said_in_turn_up_to_their_times_and_the_silence_ends_the_call(box: Box) -> None:
    session = a_session(box, NOBODY)
    await session.start()
    idle = Idle(says=("Are you there?", "Hello?"), after_s=5.0, times=3)
    await clock.watch_the_quiet(session, idle, 30, sleep=ticking([]))
    assert said_by_the_agent(session) == ["Are you there?", "Hello?", "Are you there?"]
    assert session.ended == ("timeout", "platform")
    await session.close()


@needs_the_database
async def test_a_call_with_neither_set_is_never_watched(box: Box) -> None:
    session = a_session(box, NOBODY)
    await clock.watch_the_quiet(session, None, None, sleep=never)


@needs_the_database
async def test_whatever_the_caller_says_starts_the_silence_over(box: Box) -> None:
    session = a_session(box, NOBODY)
    await session.start()

    async def speaks_at_ten(tick: int) -> None:
        if tick == 10:
            heard(session, "sigo aquí")

    ticks: list[int] = []
    await clock.watch_the_quiet(session, None, 5, sleep=ticking(ticks, speaks_at_ten))
    await session.close()
    assert len(ticks) == 10 + 19  # the look that hears them counts as the first quiet one


@needs_the_database
async def test_the_hold_is_not_the_callers_silence(box: Box) -> None:
    session = a_session(box, NOBODY)
    await session.start()
    await apply(session, CallHold())

    async def given_back_at_forty(tick: int) -> None:
        if tick == 40:
            await apply(session, CallUnhold())

    ticks: list[int] = []
    await clock.watch_the_quiet(session, None, 5, sleep=ticking(ticks, given_back_at_forty))
    await session.close()
    assert len(ticks) == 40 + 19  # the look that finds the line given back counts as the first
