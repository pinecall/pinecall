"""A call's tools as livekit runs them: the app's, the platform's lookups, end_call, and the date."""

import json
import re
from collections.abc import Awaitable, Callable, Mapping, Sequence
from contextlib import AbstractAsyncContextManager
from datetime import date
from typing import cast

from livekit.agents import RunContext, StopResponse, ToolError, llm
from livekit.agents.beta.tools import EndCallTool
from livekit.agents.llm import FunctionCall, FunctionCallOutput
from livekit.agents.voice import AgentSession

from pinecall_runtime.agents.declaration import SAY, ToolSpec
from pinecall_runtime.exceptions import PinecallError
from pinecall_runtime.kit.text import Json, JsonObject
from pinecall_runtime.session.call import Call, ToolUse
from pinecall_runtime.session.lookups import Lookups, platform_tools
from pinecall_runtime.session.writing import WRITTEN_WITHIN_S
from pinecall_runtime.wire.events import ErrorEvent, ToolCall
from pinecall_runtime.wire.parts import StateCauseTool, ToolResult

# Runs one tool the model called and returns what the model reads of it.
type Run = Callable[[ToolUse, RunContext[None]], Awaitable[str | llm.ToolResult]]
# Says a line as a tool starts, unless the agent spoke since the caller did.
type Announce = Callable[[str | None], None]
# Whether the agent has said words since the caller last spoke.
type Spoke = Callable[[], bool]
# What plays while the caller waits: the hold melody after its grace, or nothing.
type Waiting = Callable[[], AbstractAsyncContextManager[None]]

# `error` entry code for a tool the app closed.
REFUSED = "refused"
NOT_AVAILABLE = "{name} is not available now"
END_CALL = "end_call"
# The goodbye comes in the same turn as the call to end: a reply generated after it says odd
# things, so nothing is generated.
SAY_GOODBYE_FIRST = (
    "Say your goodbye in the same reply in which you call this, before the call: nothing you "
    "say after it is heard, and nothing is generated for you."
)
# Added to every tool's schema: the model's own line for the wait, said while the tool runs when
# its answer said nothing itself. The app never receives it.
SAY_PARAMETER: JsonObject = {
    "type": "string",
    "description": (
        "One short line to the caller, in their language, said as this tool runs so they never "
        "wait in silence: what you are doing, never the answer. 'Let me check the agenda.'"
    ),
}
# A tool pair, not a system message: a system message in the middle of the conversation becomes
# a user turn for the providers that take one system text.
CLOCK_TOOL = "current_date"
CLOCK_CALL_ID = "clock_1"
WEEKDAYS = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")
# Gemini refuses a function call that neither a user turn nor a function response comes before, and
# the clock's pair opens every history: for a Google model it opens behind a user turn of one dot,
# the turn livekit's own Gemini format adds at a history's end for the same rule.
GEMINI_OPENING = "."
_A_PLACEHOLDER = re.compile(r"\{\{\s*([\w.]+)\s*\}\}")


class Toolbox:
    """The tools a call's agent holds, and what running each one does to the call."""

    def __init__(
        self,
        call: Call,
        live: AgentSession[None],
        lookups: Lookups,
        *,
        announce: Announce,
        spoke: Spoke,
        waiting: Waiting,
        hung_up_by_the_model: Callable[[], None],
    ) -> None:
        """The tools of a call nobody has spoken on yet."""
        self.call = call
        self.live = live
        self.lookups = lookups
        self.announce = announce
        self.spoke = spoke
        self.waiting = waiting
        self.hung_up_by_the_model = hung_up_by_the_model

    def declared(self) -> list[llm.Tool | llm.Toolset]:
        """The app's tools, the platform's lookups, and end_call when the agent may hang up."""
        config = self.call.config
        tools: list[llm.Tool | llm.Toolset] = [
            *as_livekit_tools(config.tools, self._run_app_tool),
            *as_livekit_tools(platform_tools(config), self._run_lookup),
        ]
        if config.hangup is not None:
            tools.append(
                EndCallTool(
                    extra_description=f"{config.hangup.when}\n{SAY_GOODBYE_FIRST}".strip(),
                    # Hidden while the agent greets, or models hang up before the caller speaks.
                    ignore_on_enter=True,
                    # Deleting the room ends the caller's SIP leg, or they hear a silent line.
                    delete_room=True,
                    end_instructions=None,
                    on_tool_called=self._ended_by_the_model,
                    on_tool_completed=_nothing_after,
                )
            )
        return tools

    # The model's words and its tool call arrive in one answer: when the answer said nothing, the
    # line it wrote for the tool, else the tool's own announcement, plays while the tool runs. The
    # read-back is said inside the tool and awaited, so it is in the history the reply is built
    # from, or the model says it again in its own words.
    # A quiet tool is a move on the caller's screen: it runs as the model calls it, while the words
    # of that answer still play, and its result is kept with no answer asked for, or the model
    # says its sentence a second time. A model that called it in silence (Gemini answers with the
    # call alone) is asked for its answer, or the move is made and nothing is said of it.
    async def _run_app_tool(self, use: ToolUse, context: RunContext[None]) -> str | llm.ToolResult:
        spec = self.call.config.tools_by_name[use.name]
        await admit_tool(self.call, use.name)
        if not spec.quiet:
            await context.wait_for_playout()
            self.announce(use.say or spec.announce)
        # The gateway writes the tool's round trip: the turn that called it is in the log first.
        await self.call.writing.flush(WRITTEN_WITHIN_S)
        cause = StateCauseTool(kind="tool", tool=use.name, call_id=use.call_id)
        self.call.cause = cause
        try:
            async with self.waiting():
                result = await self.call.platform.tool(use, context.speech_handle.id)
        # The gateway's refusal (the app gone, a guard) is the model's to read, in its own turn.
        except PinecallError as refused:
            raise ToolError(str(refused)) from refused
        finally:
            if self.call.cause == cause:
                self.call.cause = None
        text = result_text(result)
        if result.error is not None:
            raise ToolError(text)
        if spec.confirm:
            await self.live.say(read_back(spec.confirm, use.arguments, result))
        # A supervisor took the line while the tool ran: the result stays, the reply does not.
        if self.call.a_person_has_the_line:
            raise StopResponse
        return llm.ToolResult(text, reply_required=not self.spoke()) if spec.quiet else text

    async def _run_lookup(self, use: ToolUse, context: RunContext[None]) -> str:
        self.announce(use.say)
        return await self.lookups.called(use, context.speech_handle.id)

    # end_call closes the session as livekit's own initiative, which reads as a drain: the reason
    # is written down first, and the tool with it, since it never reaches the app.
    async def _ended_by_the_model(self, event: llm.Toolset.ToolCalledEvent) -> None:
        self.hung_up_by_the_model()
        context: RunContext[None] = event.ctx  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType]
        call_id = context.function_call.call_id
        called = ToolCall(call_id=call_id, name=END_CALL, arguments={}, speech_id=context.speech_handle.id)
        await self.call.writing.write("tool.call", called)
        await self.call.writing.write("tool.result", ToolResult(call_id=call_id, name=END_CALL))


def as_livekit_tools(specs: Sequence[ToolSpec], run: Run) -> list[llm.Tool]:
    """Each tool as livekit's raw-schema tool, whose callable runs it through `run`."""
    return [_raw(spec, run) for spec in specs]


async def admit_tool(call: Call, name: str) -> None:
    """Pass a tool the app left open; one it closed is an entry and the model's ToolError."""
    if name in call.open_tools:
        return
    why = NOT_AVAILABLE.format(name=name)
    await call.writing.write("error", ErrorEvent(code=REFUSED, message=why, recoverable=True))
    raise ToolError(why)


# The model reads JSON, never a language's repr of it.
def result_text(result: ToolResult) -> str:
    """What the model reads of a tool's result: its error, else its summary, else its output."""
    if result.error is not None:
        return result.error
    if result.summary is not None:
        return result.summary
    if result.output is None:
        return ""
    return output_text(result.output)


# livekit sends an output that parses as a JSON list to Anthropic as content blocks, and the
# request fails on the first block with no type: a list travels inside an object.
def output_text(output: Json) -> str:
    """A tool's output as the model reads it: a string as it is, anything else as JSON."""
    if isinstance(output, str):
        return output
    if isinstance(output, list):
        output = {"items": output}
    return json.dumps(output, ensure_ascii=False)


# `{{slot.when}}` reads `when` of the argument `slot`; a placeholder nothing fills stays as it
# was written, so the read-back never loses a word in silence.
def read_back(template: str, arguments: JsonObject, result: ToolResult) -> str:
    """The confirm template filled from what the tool was asked and what it answered."""
    data: JsonObject = {**arguments, "result": result.output}
    return _A_PLACEHOLDER.sub(lambda found: _read(data, found.group(1), found.group(0)), template)


def date_pair(today: date) -> tuple[FunctionCall, FunctionCallOutput]:
    """The call and the answer that tell the model what day it is, once per call."""
    answered = {"today": today.isoformat(), "weekday": WEEKDAYS[today.weekday()]}
    return (
        FunctionCall(call_id=CLOCK_CALL_ID, name=CLOCK_TOOL, arguments="{}"),
        # reply_required=False, or a realtime model speaks as soon as it reads the answer.
        FunctionCallOutput(
            call_id=CLOCK_CALL_ID, name=CLOCK_TOOL, output=json.dumps(answered), is_error=False, reply_required=False
        ),
    )


def opening(today: date, built: Sequence[object]) -> list[llm.ChatItem]:
    """A call's history opens with the clock's pair, behind a user turn when Gemini reads it."""
    pair: list[llm.ChatItem] = list(date_pair(today))
    if not any(_reads_like_gemini(component) for component in built):
        return pair
    return [llm.ChatMessage(role="user", content=[GEMINI_OPENING]), *pair]


async def _nothing_after(_: llm.Toolset.ToolCompletedEvent) -> None:
    raise StopResponse


# The model may sit inside the operator's request wrapper, or among a stage's fallbacks.
def _reads_like_gemini(component: object) -> bool:
    inner = getattr(component, "built", component)
    if isinstance(inner, llm.FallbackAdapter):
        return any(_reads_like_gemini(fallback) for fallback in getattr(inner, "_llm_instances", ()))
    return type(inner).__module__.startswith("livekit.plugins.google")


# The app runs its tools and ToolSpec is JSON Schema already, so the raw schema is declared; the
# callable is where the session gates and writes the call.
def _raw(spec: ToolSpec, run: Run) -> llm.Tool:
    async def call(raw_arguments: dict[str, object], context: RunContext[None]) -> str | llm.ToolResult:
        arguments: JsonObject = {name: _json(value) for name, value in raw_arguments.items()}
        line = arguments.pop(SAY, "")
        return await run(ToolUse(context.function_call.call_id, spec.name, arguments, say=str(line or "")), context)

    # A quiet tool is named by the words it runs under, so it is offered no line of its own to say.
    parameters = dict(spec.parameters) if spec.quiet else _with_a_line_to_say(spec.parameters)
    schema = {"name": spec.name, "description": spec.description, "parameters": parameters}
    return llm.function_tool(call, raw_schema=schema)


# `say` is optional: a model that wrote none leaves the tool's own announcement, if any.
def _with_a_line_to_say(parameters: Mapping[str, Json]) -> JsonObject:
    properties = parameters.get("properties")
    declared = dict(properties) if isinstance(properties, Mapping) else {}
    return {**parameters, "properties": {**declared, SAY: SAY_PARAMETER}}


def _json(value: object) -> Json:
    return cast(Json, json.loads(json.dumps(value)))


def _read(data: Json, path: str, written: str) -> str:
    found = data
    for step in path.split("."):
        if not isinstance(found, Mapping) or step not in found:
            return written
        found = found[step]
    return "" if found is None else str(found)
