"""The livekit Agent a call runs: its prompt, the ears' filter, the hooks around a turn, the lexicon read back."""

import asyncio
import contextlib
import re
from collections.abc import AsyncIterable, AsyncIterator, Mapping, Sequence
from typing import override

from livekit import rtc
from livekit.agents import llm, stt
from livekit.agents.types import NOT_GIVEN, TimedString
from livekit.agents.voice import Agent, AgentSession, ModelSettings

from pinecall_runtime.session.hearing import loops
from pinecall_runtime.session.listener import transcript_of
from pinecall_runtime.session.lookups import Lookups
from pinecall_runtime.session.prompt import Blocks, as_asked, request
from pinecall_runtime.session.repeats import SaidThisTurn, text_of, unrepeated
from pinecall_runtime.session.tools import Waiting
from pinecall_runtime.wire.events import ErrorEvent

type Heard = AsyncIterator[stt.SpeechEvent]
type Declared = list[llm.Tool | llm.Toolset]
type Thought = AsyncIterator[llm.ChatChunk | str]
type Words = AsyncIterator[str | TimedString]

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

    def __init__(
        self, live: AgentSession[None], blocks: Blocks, lookups: Lookups, declared: Declared, waiting: Waiting
    ) -> None:
        """The agent with the static blocks as its instructions and every tool of the call."""
        super().__init__(instructions=blocks.instructions, tools=declared)  # pyright: ignore[reportUnknownMemberType]
        self.live = live
        self.call = lookups.call
        self.blocks = blocks
        self.lookups = lookups
        self.waiting = waiting
        # Whether the agent said anything since the caller last spoke, its own words or a tool's
        # announcement: then no tool it calls is announced. Tools chained in one answer, each a
        # round of the model's, are announced once.
        self.said_this_turn = False
        # The sentences said since then, so no round of a tool chain says one of them again.
        self.said = SaidThisTurn()

    # Runs before the request and livekit times it, so the lookups here are the ones already
    # running (started on an interim) or quick ones. No speech handle exists yet.
    @override
    async def on_user_turn_completed(self, turn_ctx: llm.ChatContext, new_message: llm.ChatMessage) -> None:
        """Collect this turn's lookups and write the ones that did not run."""
        self.said_this_turn = False
        self.said.clear()
        for skipped in await self.lookups.turn_ended(new_message.text_content or ""):
            self.call.writing.write("error", skipped)

    # Said while the tool runs, not awaited; a turn that spoke has announced the tool itself.
    def announce(self, line: str | None) -> None:
        """Say this line as a tool starts, unless the agent has spoken since the caller did."""
        if line and not self.said_this_turn:
            self.live.say(line)
            self.said_this_turn = True
            self.said.say(line)

    # Lookups and dynamic blocks go into this request only, so the cached prefix (instructions
    # and history) stays the same bytes from turn to turn. The wait for the first token plays the
    # melody as a tool's does, and the agent's deadline cuts it, livekit's retries with it.
    @override
    async def llm_node(
        self, chat_ctx: llm.ChatContext, tools: list[llm.Tool], model_settings: ModelSettings
    ) -> Thought:
        """The model run on the history, this turn's lookups, and the dynamic blocks."""
        sent = request(chat_ctx, self.blocks, self.lookups.items)
        # A step livekit forces to answer in words (tool_choice "none") is offered no tool, as some
        # of its plugins already do: a model offered one may call it anyway, livekit drops the
        # call, and the turn ends with nothing said.
        offered = [] if model_settings.tool_choice == "none" else tools
        if self.call.context.run is not None:
            self.call.requests.append(as_asked(sent, offered))
        deadline = self.call.config.llm_timeout_s or LLM_TIMEOUT_S
        thought = Agent.default.llm_node(self, sent, offered, model_settings)
        waited = asyncio.timeout(deadline)
        async with contextlib.aclosing(thought):
            try:
                async with self.waiting(), waited:
                    first = await anext(thought, None)
            except TimeoutError:
                # A vendor's own TimeoutError is livekit's to handle, as it was before.
                if not waited.expired():
                    raise
                why = MODEL_SILENT.format(seconds=deadline)
                self.call.writing.write("error", ErrorEvent(code=LLM_TIMEOUT, message=why, recoverable=True))
                yield _late_in(self.call.config.language)
                return
            spoken: list[str] = []
            async for chunk in unrepeated(_answer(first, thought), self.said):
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
        written = unsaid(text, self.call.config.says)
        async for delta in Agent.default.transcription_node(self, written, model_settings):
            if str(delta):
                self.call.writing.write("agent.transcript", transcript_of(self.live, delta))
                self.call.agent_words.spoke(str(delta))
            yield delta

    # Before the turn detector, and before livekit counts the words that interrupt: the last point
    # to drop what is not the caller's at no cost of a model. The ears looping is never the caller;
    # the echo the canceller left (echo.py) is caught by its words; the agreement and the ears'
    # inventions only while the agent speaks, since after it stops "ok" and "thank you" are answers.
    @override
    async def stt_node(self, audio: AsyncIterable[rtc.AudioFrame], model_settings: ModelSettings) -> Heard:
        """What the ears heard, but agreement, inventions and the agent's own voice heard back."""
        async for event in Agent.default.stt_node(self, audio, model_settings):
            if not self._not_the_callers(event):
                yield event

    def _not_the_callers(self, event: stt.SpeechEvent) -> bool:
        text = event.alternatives[0].text if event.alternatives else ""
        call, policy = self.call, self.call.turn_policy
        if loops(text):
            return True
        if call.agent_speaking and (policy.is_a_backchannel(text) or policy.is_made_up(text)):
            return True
        return (call.agent_speaking or call.agent_words.just_stopped()) and call.agent_words.echoes(text)


class Unsaying:
    """The lexicon's spoken forms, matched as livekit's own replace matched the written words."""

    def __init__(self, says: Mapping[str, str]) -> None:
        """Every spoken form, longest first, mapped back to the word written."""
        self.written = {spoken.lower(): word for word, spoken in says.items() if spoken}
        keys = sorted(self.written, key=len, reverse=True)
        self.pattern = re.compile("|".join(re.escape(key) for key in keys), re.IGNORECASE)
        prefixes = {key[:n] for key in keys for n in range(1, len(key))}
        self.started = (
            re.compile("(?:" + "|".join(re.escape(p) for p in prefixes) + r")\Z", re.IGNORECASE) if prefixes else None
        )

    def back(self, text: str) -> str:
        """The text with every spoken form put back as the word written."""
        return self.pattern.sub(lambda found: self.written[found.group(0).lower()], text)

    def may_go_on(self, text: str) -> bool:
        """Whether the text ends in what the next piece could complete into a spoken form."""
        return self.started is not None and self.started.search(text) is not None

    def found(self, text: str) -> bool:
        """Whether the text holds a spoken form."""
        return self.pattern.search(text) is not None


# Pieces are held while they could still be the start of a spoken form, so a form split across
# two pieces is read back whole; a timed piece keeps the times of the first and the last.
async def unsaid(pieces: AsyncIterable[str | TimedString], says: Mapping[str, str]) -> AsyncIterator[str | TimedString]:
    """The transcript pieces with the lexicon's spoken forms read back as the words written."""
    if not says:
        async for piece in pieces:
            yield piece
        return
    unsaying = Unsaying(says)
    pending: list[str | TimedString] = []
    async for piece in pieces:
        pending.append(piece)
        text = "".join(pending)
        if unsaying.found(text) and not unsaying.may_go_on(text):
            yield _joined(pending, unsaying.back(text))
            pending = []
        elif not unsaying.may_go_on(text):
            for held in pending:
                yield held
            pending = []
    if pending:
        text = "".join(pending)
        yield _joined(pending, unsaying.back(text) if unsaying.found(text) else text)


def _joined(pending: Sequence[str | TimedString], text: str) -> str | TimedString:
    first, last = pending[0], pending[-1]
    if not isinstance(first, TimedString) or not isinstance(last, TimedString):
        return text
    end = last.end_time if last.end_time is not NOT_GIVEN else first.end_time
    return TimedString(text, start_time=first.start_time, end_time=end)


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
