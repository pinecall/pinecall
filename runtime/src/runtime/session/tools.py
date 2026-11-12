"""A call's tools as livekit runs them: the app's, the platform's lookups, a voicemail reached, end_call."""

import asyncio
import json
import re
from collections.abc import Awaitable, Callable, Generator, Mapping, Sequence
from contextlib import contextmanager

from livekit.agents import RunContext, StopResponse, ToolError, llm
from livekit.agents.beta.tools import EndCallTool

from runtime.agents.declaration import SAY, ToolSpec
from runtime.enums import Direction
from runtime.exceptions import PinecallError
from runtime.kit.text import Json, JsonObject
from runtime.session.agent import agent_of
from runtime.session.call import Call, ToolUse
from runtime.session.line import Line
from runtime.session.lookups import Lookups, platform_tools
from runtime.session.writing import WRITTEN_WITHIN_S
from runtime.wire.events import ErrorEvent, ToolCall
from runtime.wire.parts import StateCauseTool, ToolResult

# Runs one tool the model called and returns what the model reads of it.
type Run = Callable[[ToolUse, RunContext[Call]], Awaitable[str | llm.ToolResult]]

# `error` entry code for a tool the app closed.
REFUSED = "refused"
NOT_AVAILABLE = "{name} is not available now"
END_CALL = "end_call"
VOICEMAIL_TOOL = ToolSpec(
    name="voicemail_reached",
    description=(
        "Call this only when a machine answered: an answering machine or a voicemail greeting asking "
        "for a message, never a person. Say nothing yourself: the message, if the agent has one, is "
        "left for you and the call ends."
    ),
    parameters={"type": "object", "properties": {}},
    quiet=True,
)
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
_A_PLACEHOLDER = re.compile(r"\{\{\s*([\w.]+)\s*\}\}")


# Each tool finds the call it runs for where livekit keeps it (the session's userdata) and the agent
# that has the call now through the session: until 2026-11 seven callbacks were handed in for that.
class Toolbox:
    """The tools a call's agent holds, and what running each one does to the call."""

    def __init__(self, lookups: Lookups, line: Line, *, leave: Callable[[], None]) -> None:
        """The tools of a call nobody has spoken on yet; `leave` hangs up as the agent."""
        self.lookups = lookups
        self.line = line
        self.leave = leave

    def tools(self, call: Call) -> list[llm.Tool | llm.Toolset]:
        """The app's tools, the platform's lookups, and end_call when the agent may hang up."""
        declaration = call.declaration
        tools: list[llm.Tool | llm.Toolset] = [
            *as_livekit_tools(declaration.tools, self._run_app_tool),
            *as_livekit_tools(platform_tools(declaration), self._run_lookup),
        ]
        # A call somebody placed to a person is the one a machine answers instead.
        if declaration.voicemail is not None and call.context.direction is Direction.outbound:
            tools.extend(as_livekit_tools([VOICEMAIL_TOOL], self._run_voicemail))
        if declaration.hangup is not None:
            tools.append(
                EndCallTool(
                    extra_description=f"{declaration.hangup.when}\n{SAY_GOODBYE_FIRST}".strip(),
                    # Hidden while the agent greets, or models hang up before the caller speaks.
                    ignore_on_enter=True,
                    # Deleting the room ends the caller's SIP leg, or they hear a silent line.
                    delete_room=True,
                    end_instructions=None,
                    on_tool_called=_on_end_call,
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
    # A tool that hung up is the same: the goodbye came with its call, and an answer asked for after
    # it is a monologue the drain waits out (measured at 27 and 43 s) before the call can end.
    async def _run_app_tool(self, use: ToolUse, context: RunContext[Call]) -> str | llm.ToolResult:
        call, agent = context.userdata, agent_of(context.session)
        spec = call.declaration.tools_by_name[use.name]
        await admit_tool(call, use.name)
        if not spec.quiet:
            await context.wait_for_playout()
            agent.announce(use.say or spec.announce)
        # The gateway writes the tool's round trip: the turn that called it is in the log first.
        await call.writing.flush(WRITTEN_WITHIN_S)
        cause = StateCauseTool(kind="tool", tool=use.name, call_id=use.call_id)
        call.cause = cause
        try:
            async with self.line.waiting():
                with self._reminding(spec, context):
                    result = await call.platform.run_tool(use, context.speech_handle.id)
        # The gateway's refusal (the app gone, a guard) is the model's to read, in its own turn.
        except PinecallError as refused:
            await self._say_it_failed(spec, context)
            raise ToolError(str(refused)) from refused
        finally:
            if call.cause == cause:
                call.cause = None
        text = result_text(result)
        if result.error is not None:
            await self._say_it_failed(spec, context)
            raise ToolError(text)
        if spec.confirm:
            await context.session.say(read_back(spec.confirm, use.arguments, result))
        # Somebody took the line while the tool ran: the result stays, the reply does not.
        if not self.line.agent_may_speak:
            raise StopResponse
        if spec.quiet or call.ended is not None:
            return llm.ToolResult(text, reply_required=not agent.said_this_turn)
        return text

    # The tool's line for a wait grown long, said once at its moment while the tool still runs.
    @contextmanager
    def _reminding(self, spec: ToolSpec, context: RunContext[Call]) -> Generator[None]:
        if spec.delayed is None:
            yield
            return
        reminder = asyncio.get_running_loop().call_later(spec.delayed_after_s, self._remind, spec.delayed, context)
        try:
            yield
        finally:
            reminder.cancel()

    def _remind(self, line: str, context: RunContext[Call]) -> None:
        if self.line.agent_may_speak:
            agent_of(context.session).interject(line)

    # The tool's line for a failure, said and awaited before the model reads why, as a receipt is:
    # in the history the reply is built from, or the model says it again in its own words.
    async def _say_it_failed(self, spec: ToolSpec, context: RunContext[Call]) -> None:
        if spec.failed and self.line.agent_may_speak:
            await context.session.say(spec.failed)

    async def _run_lookup(self, use: ToolUse, context: RunContext[Call]) -> str:
        agent_of(context.session).announce(use.say)
        return await self.lookups.answer_the_model(use, context.speech_handle.id)

    # Never reaches the app, so the tool is written down here, as end_call is.
    async def _run_voicemail(self, use: ToolUse, context: RunContext[Call]) -> str | llm.ToolResult:
        call = context.userdata
        await write_platform_tool(call, use.name, use.call_id, context.speech_handle.id)
        await context.wait_for_playout()
        voicemail = call.declaration.voicemail
        if voicemail is not None and voicemail.message is not None:
            await context.session.say(voicemail.message, allow_interruptions=False)
        self.leave()
        raise StopResponse


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


# A tool of the platform's own never reaches the app, which writes the round trip of its own: the call
# and its empty result are written here.
async def write_platform_tool(call: Call, name: str, call_id: str, speech: str) -> None:
    """The entries of a tool the platform ran itself: called, and answered with nothing."""
    await call.writing.write("tool.call", ToolCall(call_id=call_id, name=name, arguments={}, speech_id=speech))
    await call.writing.write("tool.result", ToolResult(call_id=call_id, name=name))


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


# end_call closes the session as livekit's own initiative, which reads as a drain: the reason
# is written down first, and the tool with it, since it never reaches the app.
async def _on_end_call(event: llm.Toolset.ToolCalledEvent) -> None:
    context: RunContext[Call] = event.ctx  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType]
    call = context.userdata
    call.end_as("agent_hung_up", "agent")
    await write_platform_tool(call, END_CALL, context.function_call.call_id, context.speech_handle.id)


async def _nothing_after(_: llm.Toolset.ToolCompletedEvent) -> None:
    raise StopResponse


# The app runs its tools and ToolSpec is JSON Schema already, so the raw schema is given as it is; the
# callable is where the session gates and writes the call.
def _raw(spec: ToolSpec, run: Run) -> llm.Tool:
    async def call(raw_arguments: dict[str, object], context: RunContext[Call]) -> str | llm.ToolResult:
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
    own = dict(properties) if isinstance(properties, Mapping) else {}
    return {**parameters, "properties": {**own, SAY: SAY_PARAMETER}}


def _json(value: object) -> Json:
    decoded: Json = json.loads(json.dumps(value))
    return decoded


def _read(data: Json, path: str, written: str) -> str:
    found = data
    for step in path.split("."):
        if not isinstance(found, Mapping) or step not in found:
            return written
        found = found[step]
    return "" if found is None else str(found)
