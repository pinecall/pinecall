"""A call's history: the clock's pair it opens with, how it is rebuilt from a log, and a note added to it."""

import json
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime

from livekit.agents import llm
from livekit.agents.llm import FunctionCall, FunctionCallOutput
from livekit.agents.voice import Agent

from runtime.kit.time import now_in
from runtime.session import stages
from runtime.session.call import SPEECH, Call
from runtime.session.tools import output_text
from runtime.wire import events as wire
from runtime.wire.base import Entry

# A tool pair, not a system message: a system message in the middle of the conversation becomes
# a user turn for the providers that take one system text.
CLOCK_TOOL = "current_date"
CLOCK_CALL_ID = "clock_1"
WEEKDAYS = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")


@dataclass(frozen=True, slots=True)
class Resumption:
    """What a written call had when its session went away: the history and where it stood."""

    history: llm.ChatContext
    started_at: float | None
    turns: int
    last_said: str
    speeches: int


# ── how it opens ──


def date_pair(today: date, clock: datetime | None = None) -> tuple[FunctionCall, FunctionCallOutput]:
    """The call and the answer that tell the model what day it is, and the time where the agent is, once per call."""
    answer = {"today": today.isoformat(), "weekday": WEEKDAYS[today.weekday()]}
    if clock is not None:
        answer |= {"time": clock.strftime("%H:%M"), "timezone": str(clock.tzinfo)}
    return (
        FunctionCall(call_id=CLOCK_CALL_ID, name=CLOCK_TOOL, arguments="{}"),
        # reply_required=False, or a realtime model speaks as soon as it reads the answer.
        FunctionCallOutput(
            call_id=CLOCK_CALL_ID, name=CLOCK_TOOL, output=json.dumps(answer), is_error=False, reply_required=False
        ),
    )


def opening(today: date, built: Sequence[object], clock: datetime | None = None) -> list[llm.ChatItem]:
    """A call's history opens with the clock's pair, behind a user turn when the model asks for one."""
    return [*stages.opening_turn(built), *date_pair(today, clock)]


# An agent that says its zone reads its day and its hour there; a day a golden pinned has no hour.
def opening_of(call: Call, built: Sequence[object]) -> list[llm.ChatItem]:
    """A call's opening on its agent's own clock, when the agent says its zone."""
    zone, context = call.declaration.timezone, call.context
    if zone is None or context.pinned_day is not None:
        return opening(context.today, built)
    clock = now_in(zone)
    return opening(clock.date(), built, clock)


# ── how it is taken up again ──


# A reply cut before its turn.agent is not in the log, so it is not in the history either.
def history_of(entries: Sequence[Entry]) -> Resumption:
    """The history a written call had, rebuilt from its log in the order it was written."""
    history = llm.ChatContext.empty()
    started_at: float | None = None
    turns, last_said, speeches = 0, "", 0
    for entry in entries:
        speeches = max(speeches, _number_of(entry.data.get("speech_id")))
        match entry.type:
            case "call.started":
                started_at = wire.CallStarted.model_validate(entry.data).started_at
            case "turn.user":
                history.add_message(role="user", content=str(entry.data.get("text", "")))
            case "turn.agent":
                text = str(entry.data.get("text", ""))
                history.add_message(role="assistant", content=text)
                turns, last_said = turns + 1, text or last_said
            case "tool.call":
                history.items.append(_call_of(entry))
            case "tool.result":
                history.items.append(_output_of(entry))
            case _:
                continue
    return Resumption(history, started_at, turns, last_said, speeches)


# ── what is added to it ──


# A note joins the history as livekit appends: copy, add, update. Never a static block,
# which would spend the cache.
async def add_note(agent: Agent, note: str) -> None:
    """A note of the platform's in the agent's history, read by its next turn."""
    history = agent.chat_ctx.copy()
    history.add_message(role="system", content=note)
    await agent.update_chat_ctx(history, exclude_invalid_function_calls=False)


# A message the model is not asked to answer is in the history all the same: the next turn reads it.
async def add_unanswered(agent: Agent, text: str) -> None:
    """The contact's message in the agent's history, with no reply asked for."""
    history = agent.chat_ctx.copy()
    history.add_message(role="user", content=text)
    await agent.update_chat_ctx(history, exclude_invalid_function_calls=False)


def _number_of(speech: object) -> int:
    if isinstance(speech, str) and speech.startswith(SPEECH) and speech[len(SPEECH) :].isdigit():
        return int(speech[len(SPEECH) :])
    return 0


def _call_of(entry: Entry) -> llm.FunctionCall:
    called = wire.ToolCall.model_validate(entry.data)
    return llm.FunctionCall(
        call_id=called.call_id, name=called.name, arguments=json.dumps(called.arguments, ensure_ascii=False)
    )


def _output_of(entry: Entry) -> llm.FunctionCallOutput:
    error = entry.data.get("error")
    output = entry.data.get("output")
    return llm.FunctionCallOutput(
        call_id=str(entry.data.get("call_id", "")),
        name=str(entry.data.get("name", "")),
        output=output_text(error if error is not None else output),
        is_error=error is not None,
    )
