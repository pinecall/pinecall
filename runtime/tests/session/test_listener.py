"""The listener: the wait a reply carries, timed from the caller's last word to the first sound after it."""

import pytest
from livekit.agents import llm
from livekit.agents.llm.chat_context import MetricsReport
from livekit.agents.voice.events import ConversationItemAddedEvent, UserStateChangedEvent

from runtime.calls.log.store import Store
from runtime.session.session import Session
from tests.conftest import needs_the_database
from tests.session.conftest import NOBODY, Box, a_session


def _turn(session: Session, role: llm.ChatRole, metrics: MetricsReport) -> None:
    message = llm.ChatMessage(role=role, content=["…"], metrics=metrics)
    session.live.emit("conversation_item_added", ConversationItemAddedEvent(item=message))


def _went_quiet(session: Session, at: float) -> None:
    session.live.emit(
        "user_state_changed", UserStateChangedEvent(old_state="speaking", new_state="listening", created_at=at)
    )


async def _waits(session: Session, store: Store, call: str) -> list[object]:
    await session.end("caller_hung_up", "caller")
    entries = await store.whole_of(call)
    return [dict(entry.data["metrics"]).get("e2e_latency") for entry in entries if entry.type == "turn.agent"]


# As the simulation of 2026-10-12 had it: "let me look that up" 0.6 s after the caller, the answer
# after the tool, and livekit's e2e on the answer alone, the tool's wait in it.
@needs_the_database
async def test_a_replys_end_to_end_is_the_wait_to_its_first_sound_and_no_later_turn_has_one(
    box: Box, store: Store, call: str
) -> None:
    session = a_session(box, NOBODY)
    await session.start()
    _turn(session, "user", {"started_speaking_at": 100.0, "stopped_speaking_at": 104.0})
    _turn(session, "assistant", {"started_speaking_at": 104.6, "stopped_speaking_at": 105.5})
    _turn(session, "assistant", {"started_speaking_at": 108.2, "e2e_latency": 4.53})
    (preamble, answer) = await _waits(session, store, call)
    assert preamble == pytest.approx(0.6)
    assert answer is None


# A reply that started before the caller stopped talked over them: no wait to measure.
@needs_the_database
async def test_a_reply_over_the_caller_or_with_no_stop_known_carries_no_end_to_end(
    box: Box, store: Store, call: str
) -> None:
    session = a_session(box, NOBODY)
    await session.start()
    # The agent's opening follows no caller turn.
    _turn(session, "assistant", {"started_speaking_at": 1.0, "e2e_latency": 0.4})
    _turn(session, "user", {"stopped_speaking_at": 104.0})
    _turn(session, "assistant", {"started_speaking_at": 103.5, "e2e_latency": 1.0})
    _turn(session, "user", {})
    _turn(session, "assistant", {"started_speaking_at": 110.0, "e2e_latency": 1.0})
    assert await _waits(session, store, call) == [None, None, None]


# A realtime model's caller turn carries no `stopped_speaking_at` (Grok Voice, 2026-10-19): the
# wait is timed from when the session saw the caller go quiet, and the ears' own stop wins.
@needs_the_database
async def test_a_turn_with_no_stop_of_its_own_is_timed_from_when_the_caller_went_quiet(
    box: Box, store: Store, call: str
) -> None:
    session = a_session(box, NOBODY)
    await session.start()
    _went_quiet(session, 104.0)
    _turn(session, "user", {"started_speaking_at": 100.0})
    _turn(session, "assistant", {"started_speaking_at": 104.9})
    _went_quiet(session, 110.0)
    _turn(session, "user", {"stopped_speaking_at": 110.4})
    _turn(session, "assistant", {"started_speaking_at": 111.0})
    # Each quiet times the one turn it ended.
    _turn(session, "user", {})
    _turn(session, "assistant", {"started_speaking_at": 120.0})
    (first, second, third) = await _waits(session, store, call)
    assert (first, second, third) == (pytest.approx(0.9), pytest.approx(0.6), None)
