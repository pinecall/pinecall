"""A golden's turn held to its steps on livekit's own test run, and what livekit has no step for."""

import json
from collections.abc import Sequence
from dataclasses import dataclass

from livekit.agents.voice.run_result import ChatMessageAssert, RunAssert, RunEvent, RunResult

from runtime.evals.service.matrix import Ruling, failing, passing, score_of
from runtime.kit.text import JsonObject
from runtime.providers import service as providers
from runtime.wire.goldens import EndStep, NothingElseStep, NoToolStep, Reply, ReplyStep, Step, ToolStep
from runtime.wire.parts import EndedBy
from runtime.wire.runs import JudgeScore

TOOL = "The next tool call of the turn is {tool}{args}."
# How livekit's run says the turn holds no more events for a step to read.
NONE_LEFT = "Expected another event"
NO_TOOL = "The turn calls no {tool}."
REPLY = "The agent's next message of the turn{parts}."
END = "The call ended in this turn, by the {by}."
NOTHING_ELSE = "After the step before it, the turn holds nothing more."
NO_MODEL = "an intent needs the judge model, and none was given"

# livekit's own judge of a message (`ChatMessageAssert.judge`), in its words: the message and the
# intent, a forced yes or no, and why. Asked through the providers' one way to ask a model, so the
# judge model a run opens is the one every other question of the box is asked on. Until 2026-11 it
# was livekit's method on a model of livekit's, the one untyped call of the package.
INTENT_JUDGE = (
    "You are a test evaluator for conversational agents.\n"
    "You will be shown a message and a target intent. Determine whether the message accomplishes the intent.\n"
    "Only respond by calling the `check_intent(success: bool, reason: str)` function with your final judgment.\n"
    "Be strict: if the message does not clearly fulfill the intent, return `success = False` and explain why."
)
THE_MESSAGE = "Check if the following message fulfills the given intent.\n\nIntent:\n{intent}\n\nMessage:\n{message}"
CHECK_INTENT: JsonObject = {
    "name": "check_intent",
    "description": "Determines whether the message correctly fulfills the given intent.",
    "parameters": {
        "type": "object",
        "properties": {
            "success": {"type": "boolean", "description": "Whether the message satisfies the intent."},
            "reason": {"type": "string", "description": "A concise explanation justifying the result."},
        },
        "required": ["success", "reason"],
    },
}
ONLY_THE_CHECK = "Answer by calling check_intent, and nothing else."
THE_INTENT = "a turn's intent"
EMPTY_MESSAGE = "The chat message is empty."
NO_ARGUMENTS = "LLM did not return any arguments for evaluation."
JUDGED_NO = "Judgment failed: {reason}"


@dataclass(frozen=True, slots=True)
class TurnRun:
    """One caller line run as livekit's test run: its events, when it began, who ended the call."""

    run: RunResult[None]
    began: float
    # Set when the call ended in this turn.
    ended_by: EndedBy | None = None


@dataclass(frozen=True, slots=True)
class Checked:
    """One step's ruling, and the judge model's requests it made."""

    name: str
    criteria: str
    ruling: Ruling
    asked: int = 0


async def score_turn(
    steps: Sequence[Step], number: int, played: TurnRun, model: providers.Answerer | None
) -> list[JudgeScore]:
    """Each step in order on the turn's run, up to and with the first that broke."""
    expect = played.run.expect
    around = _list_around_a_tool(played.run.events)
    seen: dict[str, int] = {}
    scores: list[JudgeScore] = []
    for step in steps:
        for checked in await _check(step, expect, played, model, around):
            metric = _number(f"t{number}.{checked.name}", seen)
            scores.append(score_of(metric, checked.criteria, checked.ruling, asked=checked.asked))
            if not checked.ruling.passed:
                return scores
    return scores


async def _check(
    step: Step, expect: RunAssert, played: TurnRun, model: providers.Answerer | None, around: frozenset[str]
) -> list[Checked]:
    match step:
        case ToolStep():
            return [_check_tool(step, expect, played.began)]
        case NoToolStep():
            return [_check_no_tool(step, expect)]
        case ReplyStep():
            return await _check_reply(step.reply, expect, played.began, model, around)
        case EndStep():
            return [_check_end(step, played.ended_by)]
        case NothingElseStep():
            return [_check_nothing_else(expect)]


# livekit's next_event skips to the next call of any tool: that one must be this one.
def _check_tool(step: ToolStep, expect: RunAssert, began: float) -> Checked:
    args = "" if step.args is None else f" with {step.args}"
    name, criteria = f"tool:{step.tool}", TOOL.format(tool=step.tool, args=args)
    try:
        called = expect.next_event(type="function_call").event().item
    except AssertionError as broke:
        none_left = f"the turn ran no tool from here on, and the step expects {step.tool}"
        return Checked(name, criteria, failing(_word(broke, none_left)))
    given: JsonObject = json.loads(called.arguments or "{}")
    wanted = step.args or {}
    wrong = {key: given.get(key) for key, value in wanted.items() if given.get(key) != value}
    late = _say_late(called.created_at - began, step.within_ms)
    if called.name != step.tool:
        return Checked(name, criteria, failing(f"the next tool call is {called.name}, not {step.tool}"))
    if wrong:
        return Checked(name, criteria, failing(f"{step.tool} ran with {wrong}, not {step.args}"))
    if late is not None:
        return Checked(name, criteria, failing(f"{step.tool} {late}"))
    return Checked(name, criteria, passing(f"{step.tool} ran with {given}"))


# livekit's contains_function_call breaks when no call matches: here that is the step holding.
def _check_no_tool(step: NoToolStep, expect: RunAssert) -> Checked:
    name, criteria = f"no_tool:{step.no_tool}", NO_TOOL.format(tool=step.no_tool)
    try:
        expect.contains_function_call(name=step.no_tool)
    except AssertionError:
        return Checked(name, criteria, passing(f"{step.no_tool} did not run in the turn"))
    return Checked(name, criteria, failing(f"the turn forbids {step.no_tool}, and it ran"))


# The line a tool's wait is covered with is not the reply: the step reads past it to the next one.
async def _check_reply(
    reply: Reply, expect: RunAssert, began: float, model: providers.Answerer | None, around: frozenset[str]
) -> list[Checked]:
    criteria = REPLY.format(parts=_say_parts(reply))
    try:
        message = expect.next_event(type="message")
        while message.event().item.id in around:
            message = expect.next_event(type="message")
    except AssertionError as broke:
        none_left = "the turn said nothing more, and the step expects a reply"
        return [Checked("reply", criteria, failing(_word(broke, none_left)))]
    item = message.event().item
    replied = Checked("reply", criteria, _check_phrases(reply, item.text_content or "", item.created_at - began))
    if not replied.ruling.passed or reply.intent is None:
        return [replied]
    return [replied, await _check_intent(message, reply.intent, model)]


# The agent's lines around a tool: one said while a call has no output yet (its announcement, its
# `say`), and one that leads straight into a call in the same answer ("Let me look."). Neither is
# the reply a caller waits for; both are the wait's.
def _list_around_a_tool(events: Sequence[RunEvent]) -> frozenset[str]:
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


async def _check_intent(message: ChatMessageAssert, intent: str, model: providers.Answerer | None) -> Checked:
    if model is None:
        return Checked("intent", intent, failing(NO_MODEL))
    said = message.event().item.text_content
    if not said:
        return Checked("intent", intent, failing(EMPTY_MESSAGE))
    lines = [
        providers.Line("system", INTENT_JUDGE),
        providers.Line("user", THE_MESSAGE.format(intent=intent, message=said)),
    ]
    answer = await model.ask_by_tool(lines, CHECK_INTENT, insist=ONLY_THE_CHECK, what=THE_INTENT)
    if answer.arguments is None:
        return Checked("intent", intent, failing(NO_ARGUMENTS), asked=1)
    if answer.arguments.get("success") is not True:
        reason = str(answer.arguments.get("reason", ""))
        return Checked("intent", intent, failing(JUDGED_NO.format(reason=reason)), asked=1)
    return Checked("intent", intent, passing(f"it does: {said!r}"), asked=1)


def _check_phrases(reply: Reply, text: str, took_s: float) -> Ruling:
    folded = text.casefold()
    missing = [phrase for phrase in reply.says if phrase.casefold() not in folded]
    forbidden = [phrase for phrase in reply.not_said if phrase.casefold() in folded]
    accepted = not reply.says_any or any(phrase.casefold() in folded for phrase in reply.says_any)
    late = _say_late(took_s, reply.within_ms)
    if missing:
        return failing(f"it never said {_quote(missing)}: {text!r}")
    if forbidden:
        return failing(f"it said {_quote(forbidden)}: {text!r}")
    if not accepted:
        return failing(f"it said none of {_quote(reply.says_any)}: {text!r}")
    if late is not None:
        return failing(f"it {late}: {text!r}")
    return passing(repr(text))


def _check_end(step: EndStep, ended_by: EndedBy | None) -> Checked:
    criteria = END.format(by=step.end)
    if ended_by is None:
        return Checked("end", criteria, failing("the call did not end in this turn"))
    if ended_by != step.end:
        return Checked("end", criteria, failing(f"the call ended by the {ended_by}, not the {step.end}"))
    return Checked("end", criteria, passing(f"the call ended by the {ended_by}"))


def _check_nothing_else(expect: RunAssert) -> Checked:
    try:
        expect.no_more_events()
    except AssertionError as broke:
        return Checked("nothing_else", NOTHING_ELSE, failing(_first_line(broke)))
    return Checked("nothing_else", NOTHING_ELSE, passing("nothing followed"))


def _say_late(took_s: float, within_ms: int | None) -> str | None:
    took = round(took_s * 1000)
    if within_ms is None or took <= within_ms:
        return None
    return f"came {took} ms after the line, past {within_ms} ms"


# livekit's own message, without the run it appends under it.
def _first_line(broke: AssertionError) -> str:
    return str(broke).splitlines()[0] if str(broke) else "the step did not hold"


# livekit's "Expected another event, but none left." says nothing of the agent: the step says what
# the turn lacked instead. Any other sentence of livekit's is about the event found, and is kept.
def _word(broke: AssertionError, none_left: str) -> str:
    line = _first_line(broke)
    return none_left if line.startswith(NONE_LEFT) else line


def _quote(phrases: Sequence[str]) -> str:
    return ", ".join(repr(phrase) for phrase in phrases)


def _say_parts(reply: Reply) -> str:
    parts: list[str] = []
    if reply.says:
        parts.append(f" says {_quote(reply.says)}")
    if reply.says_any:
        parts.append(f" says one of {_quote(reply.says_any)}")
    if reply.not_said:
        parts.append(f" says none of {_quote(reply.not_said)}")
    if reply.within_ms is not None:
        parts.append(f" comes within {reply.within_ms} ms")
    return ";".join(parts) if parts else " comes"


# The name, with #2, #3… after its first use in the turn.
def _number(name: str, seen: dict[str, int]) -> str:
    seen[name] = seen.get(name, 0) + 1
    return name if seen[name] == 1 else f"{name}#{seen[name]}"
