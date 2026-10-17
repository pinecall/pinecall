"""A golden's turn held to its steps on livekit's own test run, and what livekit has no step for."""

import json
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Never

from livekit.agents import llm
from livekit.agents.evals import EvaluationResult, JudgmentResult
from livekit.agents.voice.run_result import ChatMessageAssert, RunAssert, RunEvent, RunResult

from pinecall_runtime.judging.schemas import JudgeScore
from pinecall_runtime.judging.service.panel import failing, passing
from pinecall_runtime.kit.text import JsonObject
from pinecall_runtime.wire.goldens import EndStep, NothingElseStep, NoToolStep, Reply, ReplyStep, Step, ToolStep
from pinecall_runtime.wire.parts import EndedBy

TOOL = "The next tool call of the turn is {tool}{args}."
NO_TOOL = "The turn calls no {tool}."
REPLY = "The agent's next message of the turn{parts}."
END = "The call ended in this turn, by the {by}."
NOTHING_ELSE = "After the step before it, the turn holds nothing more."
NO_MODEL = "an intent needs the judge model, and none was given"


@dataclass(frozen=True, slots=True)
class TurnRun:
    """One caller line run as livekit's test run: its events, when it began, who ended the call."""

    run: RunResult[None]
    began: float
    # Set when the call ended in this turn.
    ended_by: EndedBy | None = None


@dataclass(frozen=True, slots=True)
class Checked:
    """One step's verdict, and the judge model's requests it made."""

    name: str
    criteria: str
    ruling: JudgmentResult
    asked: int = 0


async def turn_scores(
    steps: Sequence[Step], number: int, played: TurnRun, model: llm.LLM[Never] | None
) -> list[JudgeScore]:
    """Each step in order on the turn's run, up to and with the first that broke."""
    expect = played.run.expect
    around = _around_a_tool(played.run.events)
    named: dict[str, int] = {}
    scores: list[JudgeScore] = []
    for step in steps:
        for checked in await _checked(step, expect, played, model, around):
            scores.append(_score(_numbered(f"t{number}.{checked.name}", named), checked))
            if not checked.ruling.passed:
                return scores
    return scores


async def _checked(
    step: Step, expect: RunAssert, played: TurnRun, model: llm.LLM[Never] | None, around: frozenset[str]
) -> list[Checked]:
    match step:
        case ToolStep():
            return [_tool(step, expect, played.began)]
        case NoToolStep():
            return [_no_tool(step, expect)]
        case ReplyStep():
            return await _reply(step.reply, expect, played.began, model, around)
        case EndStep():
            return [_end(step, played.ended_by)]
        case NothingElseStep():
            return [_nothing_else(expect)]


# livekit's next_event skips to the next call of any tool: that one must be this one.
def _tool(step: ToolStep, expect: RunAssert, began: float) -> Checked:
    args = "" if step.args is None else f" with {step.args}"
    checked = Checked(f"tool:{step.tool}", TOOL.format(tool=step.tool, args=args), passing(""))
    try:
        called = expect.next_event(type="function_call").event().item
    except AssertionError as broke:
        return _ruled(checked, failing(_first_line(broke)))
    given: JsonObject = json.loads(called.arguments or "{}")
    wanted = step.args or {}
    wrong = {key: given.get(key) for key, value in wanted.items() if given.get(key) != value}
    late = _late(called.created_at - began, step.within_ms)
    if called.name != step.tool:
        return _ruled(checked, failing(f"the next tool call is {called.name}, not {step.tool}"))
    if wrong:
        return _ruled(checked, failing(f"{step.tool} ran with {wrong}, not {step.args}"))
    if late is not None:
        return _ruled(checked, failing(f"{step.tool} {late}"))
    return _ruled(checked, passing(f"{step.tool} ran with {given}"))


# livekit's contains_function_call breaks when no call matches: here that is the step holding.
def _no_tool(step: NoToolStep, expect: RunAssert) -> Checked:
    checked = Checked(f"no_tool:{step.no_tool}", NO_TOOL.format(tool=step.no_tool), passing(""))
    try:
        expect.contains_function_call(name=step.no_tool)
    except AssertionError:
        return _ruled(checked, passing(f"{step.no_tool} did not run in the turn"))
    return _ruled(checked, failing(f"the turn forbids {step.no_tool}, and it ran"))


# The line a tool's wait is covered with is not the reply: the step reads past it to the next one.
async def _reply(
    reply: Reply, expect: RunAssert, began: float, model: llm.LLM[Never] | None, around: frozenset[str]
) -> list[Checked]:
    checked = Checked("reply", REPLY.format(parts=_parts_of(reply)), passing(""))
    try:
        message = expect.next_event(type="message")
        while message.event().item.id in around:
            message = expect.next_event(type="message")
    except AssertionError as broke:
        return [_ruled(checked, failing(_first_line(broke)))]
    item = message.event().item
    replied = _ruled(checked, _phrases(reply, item.text_content or "", item.created_at - began))
    if not replied.ruling.passed or reply.intent is None:
        return [replied]
    return [replied, await _intent(message, reply.intent, model)]


# The agent's lines around a tool: one said while a call has no output yet (its announcement, its
# `say`), and one that leads straight into a call in the same answer ("Let me look."). Neither is
# the reply a caller waits for; both are the wait's.
def _around_a_tool(events: Sequence[RunEvent]) -> frozenset[str]:
    around: set[str] = set()
    running: set[str] = set()
    leading: list[str] = []
    for event in events:
        if event.type == "function_call":
            running.add(event.item.call_id)
            around.update(leading)
            leading = []
        elif event.type == "function_call_output":
            running.discard(event.item.call_id)
            leading = []
        elif event.type == "message" and event.item.role == "assistant":
            if running:
                around.add(event.item.id)
            else:
                leading.append(event.item.id)
    return frozenset(around)


# livekit's own judge: the message and the intent, a forced yes or no, and why.
async def _intent(message: ChatMessageAssert, intent: str, model: llm.LLM[Never] | None) -> Checked:
    if model is None:
        return Checked("intent", intent, failing(NO_MODEL))
    try:
        # livekit types the judge's model as LLM[Unknown]: the one untyped call of the vendor's.
        await message.judge(model, intent=intent)  # pyright: ignore[reportUnknownMemberType]
    except AssertionError as broke:
        return Checked("intent", intent, failing(_first_line(broke)), asked=1)
    message_text = message.event().item.text_content
    return Checked("intent", intent, passing(f"it does: {message_text!r}"), asked=1)


def _phrases(reply: Reply, text: str, took_s: float) -> JudgmentResult:
    """Whether the message says what the step asks of its words, in time, and why."""
    folded = text.casefold()
    missing = [phrase for phrase in reply.says if phrase.casefold() not in folded]
    forbidden = [phrase for phrase in reply.not_said if phrase.casefold() in folded]
    accepted = not reply.says_any or any(phrase.casefold() in folded for phrase in reply.says_any)
    late = _late(took_s, reply.within_ms)
    if missing:
        return failing(f"it never said {_quoted(missing)}: {text!r}")
    if forbidden:
        return failing(f"it said {_quoted(forbidden)}: {text!r}")
    if not accepted:
        return failing(f"it said none of {_quoted(reply.says_any)}: {text!r}")
    if late is not None:
        return failing(f"it {late}: {text!r}")
    return passing(repr(text))


def _end(step: EndStep, ended_by: EndedBy | None) -> Checked:
    checked = Checked("end", END.format(by=step.end), passing(""))
    if ended_by is None:
        return _ruled(checked, failing("the call did not end in this turn"))
    if ended_by != step.end:
        return _ruled(checked, failing(f"the call ended by the {ended_by}, not the {step.end}"))
    return _ruled(checked, passing(f"the call ended by the {ended_by}"))


def _nothing_else(expect: RunAssert) -> Checked:
    checked = Checked("nothing_else", NOTHING_ELSE, passing("nothing followed"))
    try:
        expect.no_more_events()
    except AssertionError as broke:
        return _ruled(checked, failing(_first_line(broke)))
    return checked


def _late(took_s: float, within_ms: int | None) -> str | None:
    took = round(took_s * 1000)
    if within_ms is None or took <= within_ms:
        return None
    return f"came {took} ms after the line, past {within_ms} ms"


def _ruled(checked: Checked, ruling: JudgmentResult) -> Checked:
    return Checked(checked.name, checked.criteria, ruling, checked.asked)


# livekit's own message, without the run it appends under it.
def _first_line(broke: AssertionError) -> str:
    return str(broke).splitlines()[0] if str(broke) else "the step did not hold"


def _quoted(phrases: Sequence[str]) -> str:
    return ", ".join(repr(phrase) for phrase in phrases)


def _parts_of(reply: Reply) -> str:
    parts: list[str] = []
    if reply.says:
        parts.append(f" says {_quoted(reply.says)}")
    if reply.says_any:
        parts.append(f" says one of {_quoted(reply.says_any)}")
    if reply.not_said:
        parts.append(f" says none of {_quoted(reply.not_said)}")
    if reply.within_ms is not None:
        parts.append(f" comes within {reply.within_ms} ms")
    return ";".join(parts) if parts else " comes"


def _numbered(name: str, named: dict[str, int]) -> str:
    """The name, with #2, #3… after its first use in the turn."""
    named[name] = named.get(name, 0) + 1
    return name if named[name] == 1 else f"{name}#{named[name]}"


def _score(name: str, checked: Checked) -> JudgeScore:
    ruling = checked.ruling
    return JudgeScore(
        metric=name,
        score=EvaluationResult(judgments={name: ruling}).score,
        passed=ruling.passed,
        reason=ruling.reasoning,
        criteria=checked.criteria,
        judge_calls=checked.asked,
    )
