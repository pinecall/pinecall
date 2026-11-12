"""A call's history: the clock's pair it opens with, on the agent's own day, and behind a user turn for Gemini."""

import json
import locale
from collections.abc import Callable
from dataclasses import replace
from datetime import date, datetime
from typing import cast
from zoneinfo import ZoneInfo

import pytest
from livekit.agents import llm
from livekit.agents.llm._provider_format import google as gemini_format

from runtime.agents.declaration import Declaration
from runtime.enums import Channel
from runtime.kit.text import JsonObject
from runtime.providers.service.stages import llm_of
from runtime.providers.stage import Running
from runtime.session.call import CallContext
from runtime.session.history import date_pair, opening, opening_of
from runtime.session.prompt import Blocks, request
from tests.session.conftest import context_of

# ── the date ──


def test_the_date_is_a_call_and_its_answer_under_one_id_that_asks_for_no_reply() -> None:
    called, answered = date_pair(date(2026, 9, 28))
    assert (called.call_id, answered.call_id, called.name) == ("clock_1", "clock_1", "current_date")
    assert json.loads(answered.output) == {"today": "2026-09-28", "weekday": "monday"}
    assert answered.reply_required is False


def test_an_agent_that_declares_its_zone_is_told_the_hour_there_too() -> None:
    clock = datetime(2026, 9, 28, 14, 5, tzinfo=ZoneInfo("America/Los_Angeles"))
    answered = json.loads(date_pair(clock.date(), clock)[1].output)
    assert answered == {"today": "2026-09-28", "weekday": "monday", "time": "14:05", "timezone": "America/Los_Angeles"}


def test_a_call_opens_on_its_agents_own_day_and_a_pinned_day_has_no_hour() -> None:
    there = datetime(2026, 9, 28, 20, 0, tzinfo=ZoneInfo("America/Los_Angeles"))

    def now_there(_zone: str) -> datetime:
        return there

    context = context_of("call_1", Channel.web)
    zoned = Declaration(slug="desk", timezone="America/Los_Angeles")
    assert _told(zoned, context, now_there) == {
        "today": "2026-09-28",
        "weekday": "monday",
        "time": "20:00",
        "timezone": "America/Los_Angeles",
    }
    pinned = replace(context, today=date(2026, 1, 5), pinned_day=date(2026, 1, 5))
    assert _told(zoned, pinned, now_there) == {"today": "2026-01-05", "weekday": "monday"}
    assert "time" not in _told(Declaration(slug="desk"), context, now_there)


def _told(declaration: Declaration, context: CallContext, now: Callable[[str], datetime]) -> JsonObject:
    answered = opening_of(declaration, context, (), now=now)[-1]
    assert isinstance(answered, llm.FunctionCallOutput)
    return cast(JsonObject, json.loads(answered.output))


def test_the_weekday_does_not_depend_on_the_locale_of_the_process() -> None:
    before = locale.setlocale(locale.LC_TIME)
    try:
        with pytest.raises(locale.Error):
            locale.setlocale(locale.LC_TIME, "es_UY.nowhere")
        assert json.loads(date_pair(date(2026, 9, 27))[1].output)["weekday"] == "sunday"
    finally:
        locale.setlocale(locale.LC_TIME, before)


def test_the_pair_reaches_the_provider_as_a_pair_and_never_as_an_instruction() -> None:
    history = llm.ChatContext.empty()
    history.items.extend(date_pair(date(2026, 9, 28)))
    history.add_message(role="user", content="¿qué día es?")
    messages, _ = request(history, Blocks()).to_provider_format("openai")
    assert [message["role"] for message in messages] == ["assistant", "tool", "user"]


# The google plugin's own formatter reads the history: it runs where the voice extra is installed.
def test_a_gemini_history_opens_behind_a_user_turn_and_gemini_takes_it() -> None:
    pytest.importorskip("livekit.plugins.google")
    gemini = llm_of(Running("google", "k", model="gemini-3.5-flash-lite"))
    history = llm.ChatContext.empty()
    history.items.extend(opening(date(2026, 10, 11), (gemini,)))
    history.add_message(role="assistant", content="Hola, ¿en qué te ayudo?")
    history.add_message(role="user", content="¿Tienes hueco el jueves?")
    # livekit's Gemini format is untyped: named here by its shape, and read through JSON, the
    # shape Gemini receives.
    to_gemini: Callable[[llm.ChatContext], tuple[object, object]] = vars(gemini_format)["to_chat_ctx"]
    turns = json.loads(json.dumps(to_gemini(history)[0]))
    assert [turn["role"] for turn in turns][:3] == ["user", "model", "user"]
    assert "function_call" in turns[1]["parts"][0]


def test_every_other_model_opens_on_the_clock_alone() -> None:
    claude = llm_of(Running("anthropic", "k", model="claude-haiku-5-5"))
    opened = opening(date(2026, 10, 11), (claude,))
    assert [item.type for item in opened] == ["function_call", "function_call_output"]
