"""The livekit Agent a call runs: its prompt, the ears' filter, the hooks around a turn, a line said as a tool runs."""

import asyncio
import contextlib
from collections.abc import AsyncIterable, AsyncIterator, Callable
from typing import override

from livekit import rtc
from livekit.agents import llm, stt
from livekit.agents.types import NOT_GIVEN, NotGivenOr, TimedString
from livekit.agents.voice import Agent, AgentSession, ModelSettings, SpeechHandle

from runtime.providers.stage import Speaking, Thinking
from runtime.session import stages
from runtime.session.call import Call
from runtime.session.hearing import TurnPolicy, loops
from runtime.session.line import Line
from runtime.session.lookups import Lookups
from runtime.session.prompt import Blocks, as_asked, request
from runtime.session.repeats import SaidThisTurn, drop_repeats, text_of
from runtime.session.transcript import transcript_of, unsay
from runtime.wire.events import ErrorEvent

type Heard = AsyncIterator[stt.SpeechEvent]
type Thought = AsyncIterator[llm.ChatChunk | str]
type Words = AsyncIterator[str | TimedString]
# The history an agent takes over from the one before it, read when asked: the conversation as it stands then.
type Carry = Callable[[], llm.ChatContext]

LLM_TIMEOUT = "llm_timeout"
MODEL_SILENT = "the model said nothing within {seconds:g}s, so the caller was asked to say it again"
# How long a turn waits for the model's first word when the agent sets no deadline: past it the
# caller hears MODEL_LATE instead of a silence a model stuck for 20 s would leave them in.
LLM_TIMEOUT_S = 12.0
# What the caller hears when the model is past the deadline, by the agent's language; English
# where the agent's language has no sentence here.
MODEL_LATE = {
    "es": "Disculpe, me demoré. ¿Me lo repite, por favor?",
    "en": "Sorry, that took me too long. Could you say that again?",
    "pt": "Desculpe, demorei. Pode repetir, por favor?",
}


class CallAgent(Agent):
    """livekit's Agent reading the call's prompt blocks, lookups and tools."""

    # A model or a voice given here is this agent's own, over the session's: how a stage rebuilt in the
    # middle of a call takes over, livekit handing the call from the agent before to this one.
    def __init__(
        self,
        live: AgentSession[Call],
        blocks: Blocks,
        lookups: Lookups,
        tools: list[llm.Tool | llm.Toolset],
        line: Line,
        policy: TurnPolicy,
        *,
        thinking: NotGivenOr[Thinking] = NOT_GIVEN,
        voice: NotGivenOr[Speaking] = NOT_GIVEN,
        carry: Carry | None = None,
    ) -> None:
        """The agent with the static blocks as its instructions and every tool of the call."""
        history = NOT_GIVEN if carry is None else carry()
        super().__init__(instructions=blocks.instructions, tools=tools, llm=thinking, tts=voice, chat_ctx=history)  # pyright: ignore[reportUnknownMemberType]
        self.live = live
        self.thinking, self.voice = thinking, voice
        self.carry = carry
        self.call = live.userdata
        self.blocks = blocks
        self.lookups = lookups
        self.line = line
        self.policy = policy
        # Whether the agent said anything since the caller last spoke, its own words or a tool's
        # announcement: then no tool it calls is announced. Tools chained in one answer, each a
        # round of the model's, are announced once.
        self.said_this_turn = False
        # The sentences said since then, so no round of a tool chain says one of them again.
        self.said = SaidThisTurn()
        # A tool's announcement with its line, from when it is said until it has played: livekit writes it into
        # the history only then, and the reply asked for meanwhile is built with it (`llm_node`), or the model
        # says it again.
        self.saying: list[tuple[SpeechHandle, str]] = []

    # The one start of a caller's turn, spoken or written: livekit's end-of-turn hook calls it for a
    # spoken turn, the session for a written one (livekit's generate_reply never runs the hook). Until
    # 2026-11 the written copy forgot what was still being said, and a message written in a worker's
    # room ran neither.
    async def begin_turn(self, text: str) -> None:
        """The caller spoke: forget what was said since they last did, and collect this turn's lookups."""
        self.said_this_turn = False
        self.said.clear()
        self.saying.clear()
        for skipped in await self.lookups.end_turn(text):
            self.call.writing.write("error", skipped)

    # Runs before the request and livekit times it, so the lookups here are the ones already
    # running (started on an interim) or quick ones. No speech handle exists yet.
    @override
    async def on_user_turn_completed(self, turn_ctx: llm.ChatContext, new_message: llm.ChatMessage) -> None:
        """Collect this turn's lookups and write the ones that did not run."""
        await self.begin_turn(new_message.text_content or "")

    # livekit starts this agent once the one before it has said its last reply: what was said after the
    # hand-over was asked for is on that agent's history only then, and is read here.
    @override
    async def on_enter(self) -> None:
        """Take the history the agent before this one ended on."""
        if self.carry is not None:
            await self.update_chat_ctx(self.carry(), exclude_invalid_function_calls=False)

    # The turn's own memory goes with it: a line said before the hand-over is not said again after.
    def succeed_with(self, carry: Carry, thinking: Thinking | None, voice: Speaking | None) -> "CallAgent":
        """The same agent on a new model or a new voice, each kept where none is given, the history carried on."""
        heir = CallAgent(
            self.live,
            self.blocks,
            self.lookups,
            list(self.tools),
            self.line,
            self.policy,
            thinking=self.thinking if thinking is None else thinking,
            voice=self.voice if voice is None else voice,
            carry=carry,
        )
        heir.said_this_turn, heir.said, heir.saying = self.said_this_turn, self.said, self.saying
        return heir

    # Said while the tool runs, not awaited; a turn that spoke has announced the tool itself.
    def announce(self, line: str | None) -> None:
        """Say this line as a tool starts, unless the agent has spoken since the caller did."""
        if line and not self.said_this_turn:
            self.interject(line)

    def interject(self, line: str) -> None:
        """Say this line now, whatever was said since the caller spoke: a wait that has grown long."""
        self.saying.append((self.live.say(line), line))
        self.said_this_turn = True
        self.said.say(line)

    # The app's words are the agent's for this turn: a quiet tool that said them asks the model for no
    # other answer, and no round of the model says them again.
    def count_as_said(self, text: str) -> None:
        """Words the app had the agent say count as said this turn."""
        self.said_this_turn = True
        self.said.say(text)

    # Lookups and dynamic blocks go into this request only, so the cached prefix (instructions
    # and history) stays the same bytes from turn to turn. The wait for the first token plays the
    # melody as a tool's does, and the agent's deadline cuts it, livekit's retries with it.
    @override
    async def llm_node(
        self, chat_ctx: llm.ChatContext, tools: list[llm.Tool], model_settings: ModelSettings
    ) -> Thought:
        """The model run on the history, this turn's lookups, and the dynamic blocks."""
        # What is still playing is not in the history yet: it is sent as said, once; played, livekit keeps it.
        self.saying = [(speech, line) for speech, line in self.saying if not speech.chat_items]
        spliced = self.lookups.items
        # The platform ran these calls, not the model: a model that checks who wrote a call takes them signed.
        stages.sign_calls(self._models(), [item.call_id for item in spliced if isinstance(item, llm.FunctionCall)])
        sent = request(chat_ctx, self.blocks, spliced, [line for _, line in self.saying])
        # A step livekit forces to answer in words (tool_choice "none") is offered no tool, as some
        # of its plugins already do: a model offered one may call it anyway, livekit drops the
        # call, and the turn ends with nothing said.
        offered = [] if model_settings.tool_choice == "none" else tools
        if self.call.context.run is not None:
            self.call.requests.append(as_asked(sent, offered))
        deadline = self.call.declaration.llm_timeout_s or LLM_TIMEOUT_S
        thought = Agent.default.llm_node(self, sent, offered, model_settings)
        waiting = asyncio.timeout(deadline)
        async with contextlib.aclosing(thought):
            try:
                async with self.line.waiting(), waiting:
                    first = await anext(thought, None)
            except TimeoutError:
                # A vendor's own TimeoutError is livekit's to handle, as it was before.
                if not waiting.expired():
                    raise
                why = MODEL_SILENT.format(seconds=deadline)
                self.call.writing.write("error", ErrorEvent(code=LLM_TIMEOUT, message=why, recoverable=True))
                yield _late_in(self.call.declaration.language)
                return
            spoken: list[str] = []
            async for chunk in drop_repeats(_answer(first, thought), self.said):
                self.said_this_turn |= _has_words(chunk)
                spoken.append(text_of(chunk))
                yield chunk
            self.said.say("".join(spoken))

    # Runs on what was played, so an interrupted reply's transcript stops where its audio did; a
    # written call plays everything. Aligned speech yields one timed string per word, and the
    # voice's words are the lexicon's spoken forms: they are read back as the words written.
    @override
    async def transcription_node(self, text: AsyncIterable[str | TimedString], model_settings: ModelSettings) -> Words:
        """Each played piece of the reply, written as it plays, then passed on."""
        written = unsay(text, self.call.declaration.says)
        async for delta in Agent.default.transcription_node(self, written, model_settings):
            if str(delta):
                self.call.writing.write("agent.transcript", transcript_of(self.live, delta))
                self.call.agent_words.spoke(str(delta))
            yield delta

    # Before the turn detector, and before livekit counts the words that interrupt: the last point
    # to drop what is not the caller's at no cost of a model. The ears looping is never the caller;
    # the echo the canceller left (echo.py) is caught by its words; the agreement only while the
    # agent speaks, since after it stops "ok" is an answer.
    @override
    async def stt_node(self, audio: AsyncIterable[rtc.AudioFrame], model_settings: ModelSettings) -> Heard:
        """What the ears heard, but agreement and the agent's own voice heard back."""
        async for event in Agent.default.stt_node(self, audio, model_settings):
            if not self._is_not_the_callers(event):
                yield event

    def _is_not_the_callers(self, event: stt.SpeechEvent) -> bool:
        text = event.alternatives[0].text if event.alternatives else ""
        call = self.call
        if loops(text):
            return True
        if call.agent_speaking and self.policy.is_a_backchannel(text):
            return True
        return (call.agent_speaking or call.agent_words.just_stopped()) and call.agent_words.echoes(text)

    # The model this agent thinks with: its own when a stage was rebuilt for it, else the session's.
    def _models(self) -> list[object]:
        if self.thinking is not NOT_GIVEN:
            return [self.thinking]
        return [self.live.llm]  # pyright: ignore[reportUnknownMemberType]


# A call's session is started on a CallAgent and handed to no other (Session.start, Session.take_stages):
# a tool reaches the agent that has the call now through livekit, never through one kept from before.
def agent_of(live: AgentSession[Call]) -> CallAgent:
    """The agent that has the call now, as livekit says: the one before it until a hand-over is made."""
    agent = live.current_agent
    if not isinstance(agent, CallAgent):
        raise TypeError(
            f"a call's session runs a CallAgent and no other agent, and this one is a {type(agent).__name__}"
        )
    return agent


async def _answer(first: object, rest: AsyncIterator[object]) -> AsyncIterator[llm.ChatChunk | str]:
    """The model's answer from its first piece on: its words and its tool calls."""
    if isinstance(first, llm.ChatChunk | str):
        yield first
    async for chunk in rest:
        if isinstance(chunk, llm.ChatChunk | str):
            yield chunk


def _late_in(language: str | None) -> str:
    return MODEL_LATE.get((language or "en")[:2].lower(), MODEL_LATE["en"])


def _has_words(chunk: llm.ChatChunk | str) -> bool:
    text = chunk if isinstance(chunk, str) else (chunk.delta.content if chunk.delta else None)
    return bool(text and text.strip())
