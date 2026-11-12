"""One call on livekit's AgentSession, spoken or written: built on its place, opened, heard, re-staged and ended."""

import asyncio
import contextlib
import logging
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass

from livekit.agents import NOT_GIVEN, CloseReason, NotGivenOr, llm, stt, tts
from livekit.agents.voice import AgentSession
from livekit.agents.voice.room_io import RoomOptions, TextInputEvent, TextInputOptions
from livekit.agents.voice.run_result import RunResult

from runtime.enums import Channel, Medium, Stage
from runtime.exceptions import Conflict, Forbidden
from runtime.kit.loops import survive
from runtime.kit.text import JsonObject, sha256_of
from runtime.providers import service as providers
from runtime.providers.stage import Running, Speaking, Thinking
from runtime.session import echo, history, prompt, recording
from runtime.session.agent import CallAgent, agent_of
from runtime.session.call import Call
from runtime.session.hearing import TurnPolicy, keyterms
from runtime.session.hold import HoldMusic
from runtime.session.line import Line
from runtime.session.listener import Listener
from runtime.session.lookups import Lookups
from runtime.session.room import CallRoom, RoomCommand
from runtime.session.stages import NAME_OF, Built, is_spoken, opening_turn, sign_calls, write_switches
from runtime.session.started import start_of
from runtime.session.tools import Toolbox
from runtime.session.writing import WRITTEN_WITHIN_S
from runtime.wire import events as wire
from runtime.wire import metrics as measured
from runtime.wire.commands import AgentReply, AgentSay, CallTransfer, StateSet, name_of
from runtime.wire.parts import EndedBy, EndReason, Supervisor

logger = logging.getLogger(__name__)

# livekit's max_tool_steps: how many rounds of tools the model may chain in one answer; past them
# livekit asks for words and offers no tool. PINECALL_MAX_TOOL_STEPS sets it for a runtime.
TOOL_STEPS = 10
# livekit's close reason misreads what our code knows: a cold transfer reads as the caller
# hanging up, end_call as a drain. The reason the call was told wins; this is what is left.
HOW_IT_ENDED: dict[CloseReason, tuple[EndReason, EndedBy]] = {
    CloseReason.PARTICIPANT_DISCONNECTED: ("caller_hung_up", "caller"),
    CloseReason.ERROR: ("error", "platform"),
    CloseReason.JOB_SHUTDOWN: ("drained", "platform"),
    CloseReason.USER_INITIATED: ("drained", "platform"),
    CloseReason.TASK_COMPLETED: ("agent_hung_up", "agent"),
}
A_PLATFORM_ERROR: tuple[EndReason, EndedBy] = ("error", "platform")
NOTHING_SAID = "no reply"
NOT_HERE = "{command} acts on a call's line, and this call is written: it has no audio and no room"
NO_LINE = "a written conversation has no line to transfer"
NOT_SEALED = "call %s: its last entries did not reach the log within %gs, so it is left for the gateway to seal"
ONE_MODEL_ALONE = "this call runs on one model that hears and speaks: what its settings name now runs on the next call"
# The ears are built once a call, with the turn they end: theirs is said and waits for the next call.
REBUILT = (Stage.llm, Stage.tts)

# Told that the call was hung up, and why: whatever hosts the session ends what it runs it in.
type OnEnded = Callable[[EndReason], None]


@dataclass(frozen=True, slots=True)
class Place:
    """Where a call is had: its room, its melody, and the one participant heard; a written call in the gateway, none."""

    room: CallRoom | None = None
    melody: HoldMusic | None = None
    # The one participant the session listens to: the caller's leg, or the visitor who talks.
    participant: str | None = None


@dataclass(frozen=True, slots=True)
class Heard:
    """What came of a written message: the agent's reply, and why the call ended if it did."""

    reply: str
    ended: tuple[EndReason, EndedBy] | None = None


class Session:
    """One call's AgentSession and the call it writes: its life, what it hears, and its end."""

    # Built on its place, once: the room, the line and who is heard are known before the first entry.
    # `on_ended` is the host's (a worker's job shuts down and closes it); with none, as in the gateway,
    # a hang-up closes the session itself.
    def __init__(
        self,
        live: AgentSession[Call],
        built: tuple[Built, ...],
        lookups: Lookups,
        line: Line,
        policy: TurnPolicy,
        *,
        running: Mapping[Stage, Running],
        place: Place,
        turn: wire.TurnDetection | None = None,
        on_ended: OnEnded | None = None,
    ) -> None:
        """The session of a call nobody has spoken on, its agent holding every tool."""
        self.call = call = live.userdata
        self.live = live
        self.built = built
        # The stages as the call runs them now, read when its settings change; none on one model alone.
        self.running: dict[Stage, Running] = dict(running)
        self.lookups = lookups
        self.line = line
        self.room = place.room
        self.participant = place.participant
        # Spoken in a room, written without one: said on the call's first entry.
        self.medium = Medium.text if place.room is None else Medium.voice
        # Who ends the caller's turn on a spoken call, said on the log as it opens; a written call has none.
        self.turn = turn
        self.on_ended = on_ended
        self.blocks = prompt.Blocks(call.declaration.prompt, call.declaration.knowledge or "")
        toolbox = Toolbox(lookups, line, leave=lambda: self.hang_up("agent_hung_up", "agent"))
        self.agent = CallAgent(live, self.blocks, lookups, toolbox.tools(call), line, policy)
        self.started_at = time.time()
        self.closed = False
        # Set once close() wrote call.ended and sealed; the chat endpoint closes its socket on it.
        self.over = asyncio.Event()
        self._closing: asyncio.Task[None] | None = None
        self.recorder: recording.Recorder | None = None
        self.listener = Listener(
            live, lookups, line, dead_end=lambda: self.hang_up("error", "platform"), closing=lambda: self.closed
        )

    @property
    def ended(self) -> tuple[EndReason, EndedBy] | None:
        """Why the call ended, when our code knows: it wins over livekit's close reason."""
        return self.call.ended

    @property
    def last_heard(self) -> float:
        """When the person last said something, by the monotonic clock."""
        return self.listener.last_heard

    @property
    def usage(self) -> list[measured.ModelUsage]:
        """What the call's models used so far, as livekit last counted it."""
        return self.listener.usage

    # ── its life ──

    # call.started comes first, so it is written before livekit starts and says anything.
    async def start(self, *, notice: str | None = None, worker: str | None = None) -> None:
        """Open a new call: its first entries, the session, the notice, the greeting."""
        call = self.call
        call.writing.open()
        zone = call.declaration.timezone
        opened = start_of(call.context, self.started_at, worker, medium=self.medium, zone=zone)
        await call.writing.write("call.started", opened)
        if self.turn is not None:
            await call.writing.write("turn.detection", self.turn)
        knowledge = prompt.knowledge_changed(self.blocks)
        if knowledge is not None:
            await call.writing.write("prompt.changed", knowledge)
        await self._open(call.carried or llm.ChatContext.empty())
        if notice is not None:
            self.live.say(notice, allow_interruptions=False)
        # A call that carries another on opens in the middle of the conversation: no greeting.
        if call.carried is None:
            self._greet()
        await self.line.open()

    # The caller is in the middle of the conversation: no call.started, no greeting.
    async def resume(self, taken: history.Resumption) -> None:
        """Open a call taken up again, with the history it had and where it stood."""
        self.call.resume_from(taken.turns, taken.last_said, taken.speeches)
        if taken.started_at is not None:
            self.started_at = taken.started_at
        self.call.writing.open()
        await self._open(taken.history)
        await self.line.open()

    def hang_up(self, reason: EndReason, by: EndedBy = "agent", *, at_once: bool = False) -> None:
        """End the call for this reason: the session, and whatever hosts it."""
        self.call.end_as(reason, by)
        self.live.shutdown(drain=not at_once)
        if self.on_ended is not None:
            self.on_ended(reason)
            return
        self._closing = asyncio.create_task(self.close())

    # Said by the room when the caller left and did not come back, by their widget, or at the gateway.
    def caller_hung_up(self) -> None:
        """The caller hung up; nothing for a call that ended already (a transfer, the model's goodbye)."""
        if self.call.ended is None:
            self.hang_up("caller_hung_up", "caller")

    # The session closes first: its close writes the last turn, which comes before call.ended.
    # The log is flushed before the seal, since the gateway reads the call back from it. Nothing
    # that fails on the way keeps the call from its last entry and its seal, and `over` is set
    # whatever happens: until 2026-11 a recording that could not be finished left the call open for
    # the reaper, and the wait for call.ended was not within the log's budget.
    async def close(self) -> None:
        """Write call.ended and hand the rest to the seal, within the log's budget."""
        if self.closed:
            return
        self.closed = True
        call, name = self.call, self.call.context.call
        try:
            with survive("closing the session", name):
                await self.live.aclose()
            if self.recorder is not None:
                with survive("finishing the recording", name):
                    await self.recorder.close(self.line.read_melody())
            self.listener.stop()
            with survive("letting go of the line", name):
                await self.line.close()
            with survive("cancelling the lookups", name):
                await self.lookups.close()
            reason, by = self._how_it_ended()
            ended_at = time.time()
            ended = wire.CallEnded(reason=reason, ended_by=by, ended_at=ended_at, duration_s=ended_at - self.started_at)
            call.writing.write("call.ended", ended)
            try:
                await call.writing.flush(WRITTEN_WITHIN_S)
            except TimeoutError:
                logger.warning(NOT_SEALED, name, WRITTEN_WITHIN_S)
            else:
                await call.platform.seal(self.usage, call.last_said or NOTHING_SAID)
        finally:
            await call.writing.close(WRITTEN_WITHIN_S)
            self.over.set()

    # ── a written message ──

    # The one way a written message is heard, wherever the session runs: the gateway's chat and
    # WhatsApp call it, and livekit is told to for a message typed in a room. livekit's
    # generate_reply never runs the end-of-turn hook, so the turn begins here. While the line is not
    # the agent's, the message is written and the model is not asked.
    async def hear(self, text: str) -> Heard:
        """The contact's message into the call; the agent's reply, or nothing while the line is not the agent's."""
        call = self.call
        if not self.line.agent_may_speak:
            heard = wire.UserTurnEnded(
                speech_id=call.speech(), text=text, metrics=measured.UserTurnMetrics.model_validate({})
            )
            await call.writing.write("turn.user", heard)
            await history.add_unanswered(self.agent, text)
            return Heard("", call.ended)
        await agent_of(self.live).begin_turn(text)
        reply = self.live.generate_reply(user_input=text)
        await reply
        replies = (
            item
            for item in reversed(reply.chat_items)
            if isinstance(item, llm.ChatMessage) and item.role == "assistant"
        )
        said = next((item.text_content or "" for item in replies), "")
        # The model hung up in this turn (end_call): a hosted call ends with its host, one nothing hosts
        # here, once its last reply is said.
        if call.ended is not None and not self.closed and self.on_ended is None:
            await self.close()
        return Heard(said, call.ended)

    # A golden's line: the same turn as `hear`, run as livekit's test run so its events can be asserted.
    async def run(self, text: str) -> RunResult[None]:
        """The caller's line into the call as livekit's test run: every event the turn produced."""
        await agent_of(self.live).begin_turn(text)
        return await self.live.run(user_input=text)  # pyright: ignore[reportUnknownVariableType]

    # The session's close writes the rest: call.ended, then the seal.
    async def end(self, reason: EndReason, by: EndedBy) -> None:
        """End a call for this reason and close it."""
        self.hang_up(reason, by)
        await self.close()

    # ── what the app and a supervisor ask of it ──

    # Only a change of the static text rewrites the instructions: identical bytes would still
    # cost a cache write. The dynamic blocks are read by each request.
    async def set_prompt(self, name: str, text: str) -> None:
        """Rewrite one block; the log keeps its hash."""
        if self.blocks.set(name, text):
            await self.agent.update_instructions(self.blocks.instructions)
        changed = wire.PromptChanged(name=name, hash=sha256_of(text), chars=len(text))
        await self.call.writing.write("prompt.changed", changed)

    async def set_state(self, wanted: StateSet) -> None:
        """The app's whole state, written, and the names it holds told to the ears."""
        await self.call.set_state(wanted)
        self._tell_the_ears(wanted.state)

    # Refused while the line is not the agent's: its audio is off, so the words would be generated,
    # written as a turn and never heard (until 2026-11 they were).
    def say(self, wanted: AgentSay) -> None:
        """The app's words, said now as the agent's."""
        self.line.refuse_unless_the_agents("agent.say")
        self.agent.count_as_said(wanted.text)
        self.live.say(wanted.text, allow_interruptions=or_not_given(wanted.allow_interruptions))

    def reply(self, wanted: AgentReply) -> None:
        """The model asked to speak now, on the app's instruction."""
        self.line.refuse_unless_the_agents("agent.reply")
        allowed = or_not_given(wanted.allow_interruptions)
        self.live.generate_reply(instructions=wanted.instructions, allow_interruptions=allowed)

    async def note(self, note: str) -> None:
        """A note of the platform's in the history, read by the agent's next turn."""
        await history.add_note(self.agent, note)

    def room_or_refuse(self, command: RoomCommand | CallTransfer) -> CallRoom:
        """The call's room, or the refusal of a verb that needs one on a written call."""
        if self.room is None:
            raise Forbidden(NOT_HERE.format(command=name_of(command)))
        return self.room

    # A transfer however it was asked has one outcome entry; a supervisor's is written first, with
    # the mode resolved, and ends the call as theirs. A cold one removes the caller, which livekit
    # reads as a hang-up. The agent's transfer on a written conversation fails as any transfer does,
    # call.transferred with ok false and no mode, so the app reads one outcome entry; a supervisor's
    # is refused.
    async def transfer(self, wanted: CallTransfer, *, by: Supervisor | None = None) -> None:
        """Send the caller on, or dial the person in and leave the line to them."""
        writing = self.call.writing
        if self.room is None and by is None:
            failed = wire.CallTransferred(to=wanted.to, mode=None, ok=False, error=NO_LINE)
            await writing.write("call.transferred", failed)
            return
        room = self.room_or_refuse(wanted)
        if by is not None:
            mode = await room.mode_of(wanted)
            await writing.write("supervisor.transferred", wire.SupervisorTransferred(by=by, to=wanted.to, mode=mode))
            wanted = CallTransfer(to=wanted.to, mode=mode)
        transferred = await room.transfer(wanted, self.live)
        await writing.write("call.transferred", transferred)
        if not transferred.ok:
            return
        ended_by: EndedBy = "agent" if by is None else "supervisor"
        self.call.end_as("transferred", ended_by)
        if transferred.mode == "warm":
            await self.line.bridge()
            room.when_the_person_leaves(wanted.to, lambda: self.hang_up("transferred", ended_by))

    # ── its stages, taken anew ──

    # Built before anything of the call is touched: a stage its vendor refuses (a key, a voice it does
    # not have) leaves the call on the stages it had, and the refusal is the caller's to write.
    # livekit hands the call from the agent before to its successor once the reply being said is over,
    # so no sentence changes voice in the middle.
    async def take_stages(self, wanted: Mapping[Stage, Running], *, alone: bool) -> list[Stage]:
        """Rebuild the model and the voice that differ, and say every stage that changed; the stages rebuilt."""
        if alone or not self.running:
            raise Conflict(ONE_MODEL_ALONE)
        differs = [stage for stage, running in self.running.items() if stage in wanted and wanted[stage] != running]
        changed = [stage for stage in differs if stage in REBUILT]
        if changed:
            thinking = providers.build_thinking(wanted[Stage.llm]) if Stage.llm in changed else None
            voice = providers.build_voice(wanted[Stage.tts]) if Stage.tts in changed else None
            self._hand_over(thinking, voice)
        for stage in differs:
            now = self.running[stage] = wanted[stage]
            said = wire.StageChanged(
                stage=NAME_OF[stage], vendor=now.vendor, model=now.model, voice=now.voice, applied=stage in REBUILT
            )
            await self.call.writing.write("stage.changed", said)
        return changed

    def _hand_over(self, thinking: Thinking | None, voice: Speaking | None) -> None:
        before = self.built
        fresh: tuple[Built, ...] = tuple(component for component in (thinking, voice) if component is not None)
        built = self.built = (*(each for each in before if not _is_replaced(each, thinking, voice)), *fresh)
        self.listener.measure(built)
        write_switches(self.call.writing, fresh)
        was = self.agent
        opens = [] if opening_turn(before) else opening_turn(built)

        # Read as the hand-over is asked and again as livekit makes it, the reply being said then over.
        def carry() -> llm.ChatContext:
            carried = was.chat_ctx.copy()
            carried.items[:0] = opens
            # A model reads the calls the one before it made: one that checks them takes them signed as the platform's.
            sign_calls(built, [item.call_id for item in carried.items if isinstance(item, llm.FunctionCall)])
            return carried

        self.agent = was.succeed_with(carry, thinking, voice)
        self.live.update_agent(self.agent)

    # ── private ──

    def _greet(self) -> None:
        greeting = prompt.greeting_for(self.call.declaration.greeting, self.call.context.run)
        if greeting is not None and greeting.say is not None:
            self.live.say(greeting.say, allow_interruptions=prompt.interruptible(greeting))
        elif greeting is not None and greeting.reply is not None:
            # An empty instruction leaves the model to open on its prompt alone.
            instructions = or_not_given(greeting.reply or None)
            self.live.generate_reply(instructions=instructions, allow_interruptions=prompt.interruptible(greeting))

    # The caller is pinned before livekit subscribes, or it links the first participant of a kind it
    # accepts, a supervisor as soon as a caller. A written call in a room hears no audio, and a
    # message typed there is heard as one typed anywhere (`hear`): left to livekit's own handler it
    # skipped the turn's start, its lookups and the line (until 2026-11).
    # `record` is said: left unset, livekit asks its cloud; the call's own recorder is ours. A
    # visitor who left may come back (docs/protocol/tokens.md): their call waits, not livekit. No
    # session host: it hands every participant the raw turns, the tools and the prompt (projections.md).
    async def _open(self, opens_on: llm.ChatContext) -> None:
        spoken = is_spoken(self.live, self.built)
        channel = self.call.context.channel
        options = RoomOptions(
            participant_identity=or_not_given(self.participant),
            close_on_disconnect=channel is not Channel.web,
            audio_input=NOT_GIVEN if spoken else False,
            audio_output=NOT_GIVEN if spoken else False,
            text_input=TextInputOptions(text_input_cb=self._on_text_input),
        )
        room = NOT_GIVEN if self.room is None else self.room.room
        self.listener.listen(self.built)
        await self.live.start(self.agent, room=room, room_options=options, record=False, session_host=False)  # pyright: ignore[reportUnknownMemberType]
        echo.cancel(self.live, channel)
        if self.room is not None:
            self.recorder = await recording.record(self.live, self.call.recording, self.room.room, self.room.kind_of)
        given = opens_on.copy()
        given.items[:0] = history.opening_of(self.call, self.built)
        await self.agent.update_chat_ctx(given, exclude_invalid_function_calls=False)

    # What is being said is cut first, as livekit's own handler does for a typed message.
    async def _on_text_input(self, live: AgentSession[Call], event: TextInputEvent) -> None:
        with contextlib.suppress(RuntimeError):
            await live.interrupt()
        await self.hear(event.text)

    # Names the state holds (a patient's) join the agent's own words; livekit replaces the
    # session's keyterms in place.
    def _tell_the_ears(self, state: JsonObject) -> None:
        ears = next((component for component in self.built if isinstance(component, stt.STT)), None)
        if ears is not None and ears.capabilities.keyterms:
            self.live.update_options(keyterms=keyterms(self.call.declaration, state))

    def _how_it_ended(self) -> tuple[EndReason, EndedBy]:
        if self.call.ended is not None:
            return self.call.ended
        closed_for = self.listener.closed_for
        return A_PLATFORM_ERROR if closed_for is None else HOW_IT_ENDED[closed_for]


def or_not_given[T](value: T | None) -> NotGivenOr[T]:
    """The value, or livekit's NOT_GIVEN when it is None."""
    return NOT_GIVEN if value is None else value


def _is_replaced(component: Built, thinking: Thinking | None, voice: Speaking | None) -> bool:
    return (thinking is not None and isinstance(component, llm.LLM)) or (
        voice is not None and isinstance(component, tts.TTS)
    )
