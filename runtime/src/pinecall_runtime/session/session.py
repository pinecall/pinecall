"""One call on livekit's AgentSession, spoken or written: its life, the app's commands, the line, a supervisor."""

import asyncio
import contextlib
import time
from collections.abc import AsyncGenerator

from livekit.agents import NOT_GIVEN, CloseReason, NotGivenOr, get_job_context, llm, stt, utils
from livekit.agents.voice import AgentSession
from livekit.agents.voice.room_io import RoomOptions

from pinecall_runtime.agents.declaration import block_hash
from pinecall_runtime.calls.context import CallContext
from pinecall_runtime.enums import Channel, Direction, Medium
from pinecall_runtime.exceptions import Forbidden, ValidationError
from pinecall_runtime.kit.text import JsonObject
from pinecall_runtime.session import echo, prompt, recording
from pinecall_runtime.session.agent import CallAgent
from pinecall_runtime.session.hearing import keyterms
from pinecall_runtime.session.hold import HoldMusic
from pinecall_runtime.session.listener import Built, Listener, is_spoken
from pinecall_runtime.session.lookups import Lookups
from pinecall_runtime.session.room import CallRoom
from pinecall_runtime.session.tools import Toolbox, opening
from pinecall_runtime.session.writing import WRITTEN_WITHIN_S
from pinecall_runtime.telephony import service as telephony
from pinecall_runtime.wire import events as wire
from pinecall_runtime.wire import metrics as measured
from pinecall_runtime.wire.base import WireModel
from pinecall_runtime.wire.commands import (
    AgentReply,
    AgentSay,
    CallAttention,
    CallCallback,
    CallEvent,
    CallHangup,
    CallHold,
    CallLog,
    CallTransfer,
    CallUnhold,
    EndVerb,
    PromptSet,
    ReleaseVerb,
    SayVerb,
    SessionConfigure,
    StateSet,
    SupervisorVerb,
    TakeoverVerb,
    ToolsSet,
    TransferVerb,
    WhisperVerb,
)
from pinecall_runtime.wire.parts import EndedBy, EndReason, Supervisor

# livekit's max_tool_steps: the step after a tool round is forced to answer in words, so the agent
# does not keep talking after it answered.
ONE_ANSWER_PER_TOOL = 1
# livekit's close reason misreads what our code knows: a cold transfer reads as the caller
# hanging up, end_call as a drain. The reason recorded wins; this is what is left.
HOW_IT_ENDED: dict[CloseReason, tuple[EndReason, EndedBy]] = {
    CloseReason.PARTICIPANT_DISCONNECTED: ("caller_hung_up", "caller"),
    CloseReason.ERROR: ("error", "platform"),
    CloseReason.JOB_SHUTDOWN: ("drained", "platform"),
    CloseReason.USER_INITIATED: ("drained", "platform"),
    CloseReason.TASK_COMPLETED: ("agent_hung_up", "agent"),
}
A_PLATFORM_ERROR: tuple[EndReason, EndedBy] = ("error", "platform")
NOTHING_SAID = "no reply"
ALREADY_HELD = "{id} already holds the line; they release it, or nobody does"
NOBODY_HOLDS = "nobody holds the line, so there is nothing to give back"
ALREADY_WAITING = "the caller is already waiting for a person"
# The app's tool timeout must outlast the wait it asks for; the runtime does not extend it.
NOBODY_TOOK_IT = "nobody took the line within {wait_s:g}s"
NOT_HERE = "{command} is not something this call does"


class Session:
    """One call's AgentSession and the call it writes: its events, commands, time and end."""

    def __init__(self, live: AgentSession[None], built: tuple[Built, ...], lookups: Lookups) -> None:
        """The session of a call nobody has spoken on, its agent holding every tool."""
        self.call = lookups.call
        self.live = live
        self.built = built
        self.lookups = lookups
        self.blocks = prompt.Blocks(self.call.config.prompt, self.call.config.knowledge or "")
        toolbox = Toolbox(
            self.call,
            live,
            lookups,
            announce=self._announce,
            waiting=self._music,
            hung_up_by_the_model=self._hung_up_by_the_model,
        )
        self.agent = CallAgent(live, self.blocks, lookups, toolbox.declared(), self._music)
        self.started_at = time.time()
        # Why the call ended, when our code knows: it wins over livekit's close reason.
        self.ended: tuple[EndReason, EndedBy] | None = None
        self.closed = False
        # Set once close() wrote call.ended and sealed; the chat endpoint closes its socket on it.
        self.over = asyncio.Event()
        self.closing: asyncio.Task[None] | None = None
        self.on_hold = False
        self.waiting: asyncio.Task[None] | None = None
        # Given at start; a written call has neither.
        self.room: CallRoom | None = None
        self.hold: HoldMusic | None = None
        # The one participant the session listens to: the caller's leg, or the talk seat.
        self.seat: str | None = None
        self.recorder: recording.Recorder | None = None
        self.listener = Listener(self.call, live, lookups, None, dead_end=lambda: self.hang_up("error", "platform"))

    @property
    def last_heard(self) -> float:
        """When the person last said something, by the monotonic clock."""
        return self.listener.last_heard

    # ── the session's life ──

    # call.started comes first, so it is written before livekit starts and says anything.
    async def start(
        self,
        *,
        room: CallRoom | None = None,
        hold: HoldMusic | None = None,
        seat: str | None = None,
        notice: str | None = None,
        worker: str | None = None,
    ) -> None:
        """Open a new call: its first entries, the session, the notice, the greeting."""
        self.room, self.hold, self.seat = room, hold, seat
        self.call.writing.open()
        medium = Medium.text if room is None else Medium.voice
        await self.call.writing.write(
            "call.started", _started(self.call.context, self.started_at, worker, medium=medium)
        )
        knowledge = prompt.knowledge_changed(self.blocks)
        if knowledge is not None:
            await self.call.writing.write("prompt.changed", knowledge)
        await self._open(self.call.carried or llm.ChatContext.empty())
        if notice is not None:
            self.live.say(notice, allow_interruptions=False)
        # A call that carries another on opens in the middle of the conversation: no greeting.
        if self.call.carried is not None:
            return
        greeting = prompt.greeting_for(self.call.config.greeting, self.call.context.run)
        if greeting is not None and greeting.say is not None:
            self.live.say(greeting.say, allow_interruptions=prompt.interruptible(greeting))
        elif greeting is not None and greeting.reply is not None:
            # An empty instruction leaves the model to open on its prompt alone.
            instructions = given_or_unset(greeting.reply or None)
            self.live.generate_reply(instructions=instructions, allow_interruptions=prompt.interruptible(greeting))

    # The caller is in the middle of the conversation: no call.started, no greeting.
    async def resume(self, history: llm.ChatContext) -> None:
        """Open a call taken up again, with the history it had."""
        self.call.writing.open()
        await self._open(history)

    # In a worker the job's shutdown closes the session; a written call in the gateway has no
    # job, so the hang-up closes it itself.
    def hang_up(self, reason: EndReason, by: EndedBy = "agent", *, at_once: bool = False) -> None:
        """End the call for this reason: the session, and the job that runs it."""
        self.ended = (reason, by)
        self.live.shutdown(drain=not at_once)
        job = get_job_context(required=False)
        if job is not None:
            job.shutdown(reason=reason)
            return
        self.closing = asyncio.create_task(self.close())

    # The session closes first: its close writes the last turn, which comes before call.ended.
    # The log is flushed before the seal, since the gateway reads the call back from it.
    async def close(self) -> None:
        """Write call.ended and hand the rest to the seal, within the log's budget."""
        if self.closed:
            return
        self.closed = True
        await self.live.aclose()
        if self.recorder is not None:
            await self.recorder.close(self.hold)
        self.listener.stop()
        if self.waiting is not None:
            await utils.aio.cancel_and_wait(self.waiting)
        await self.lookups.close()
        reason, by = self._how_it_ended()
        ended_at = time.time()
        ended = wire.CallEnded(reason=reason, ended_by=by, ended_at=ended_at, duration_s=ended_at - self.started_at)
        try:
            await self.call.writing.write("call.ended", ended)
            await self.call.writing.flush(WRITTEN_WITHIN_S)
            await self.call.platform.seal(self.usage, self.call.last_said or NOTHING_SAID)
        finally:
            await self.call.writing.close(WRITTEN_WITHIN_S)
            self.over.set()

    @property
    def usage(self) -> list[measured.ModelUsage]:
        """What the call's models used so far, as livekit last counted it."""
        return self.listener.usage

    # ── the app's commands ──

    async def apply(self, command: WireModel) -> None:
        """What one command of the app does to this call."""
        if await self._written(command) or await self._spoken(command):
            return
        if isinstance(command, SupervisorVerb):
            await self.supervise(command)
            return
        await self._in_the_room(command)

    async def _written(self, command: WireModel) -> bool:
        match command:
            case PromptSet():
                await self.set_prompt(command.name, command.text)
            case ToolsSet():
                await self.call.set_tools(command)
            case StateSet():
                await self.call.set_state(command)
                self._tell_the_ears(command.state)
            case CallEvent():
                await self.call.receive(command.name, command.data, source="app")
            case CallLog():
                await self.call.log_custom(command)
            case CallCallback():
                await self.call.call_back(command)
            case SessionConfigure():
                await self.call.configure(command)
            case _:
                return False
        return True

    async def _spoken(self, command: WireModel) -> bool:
        match command:
            case AgentSay():
                self.live.say(command.text, allow_interruptions=given_or_unset(command.allow_interruptions))
            case AgentReply():
                self.live.generate_reply(
                    instructions=command.instructions, allow_interruptions=given_or_unset(command.allow_interruptions)
                )
            case CallHangup():
                self.hang_up("agent_hung_up")
            case CallHold():
                await self.hold_the_line()
            case CallUnhold():
                await self.give_the_line_back()
            case CallAttention():
                await self.ask_for_a_person(command)
            case _:
                return False
        return True

    # Only a change of the static text rewrites the instructions: identical bytes would still
    # cost a cache write. The dynamic blocks are read by each request.
    async def set_prompt(self, name: str, text: str) -> None:
        """Rewrite one block; the log keeps its hash."""
        if self.blocks.set(name, text):
            await self.agent.update_instructions(self.blocks.instructions)
        await self.call.writing.write(
            "prompt.changed", wire.PromptChanged(name=name, hash=block_hash(text), chars=len(text))
        )

    # ── the line ──

    async def hold_the_line(self) -> None:
        """The agent neither speaks nor hears, the melody plays, and the log says so."""
        if self.on_hold:
            return
        self.on_hold = True
        await silence(self.live)
        if self.hold is not None:
            self.hold.began()
        await self.call.writing.write("call.line", wire.CallLine(held=True, muted=False))

    async def give_the_line_back(self) -> None:
        """The melody stops and the agent hears and speaks again."""
        if not self.on_hold:
            return
        self._melody_ends()
        hear_again(self.live)
        await self.call.writing.write("call.line", wire.CallLine(held=False, muted=False))

    async def stop_the_melody(self) -> None:
        """The melody stops and the line is written free; whoever took it keeps it."""
        if not self.on_hold:
            return
        self._melody_ends()
        await self.call.writing.write("call.line", wire.CallLine(held=False, muted=False))

    async def ask_for_a_person(self, wanted: CallAttention) -> None:
        """Hold the caller for a supervisor, for as long as the app asked, once at a time."""
        if self.call.waiting_for_a_person:
            raise ValidationError(ALREADY_WAITING)
        self.call.waiting_for_a_person = True
        await self.call.writing.write(
            "attention.requested", wire.AttentionRequested(reason=wanted.reason, wait_s=wanted.wait_s)
        )
        await self.hold_the_line()
        self.waiting = asyncio.create_task(self._nobody_came(wanted.wait_s))

    # ── a supervisor ──

    async def supervise(self, command: SupervisorVerb) -> None:
        """One of a supervisor's six verbs, written before it acts."""
        by, verb = command.by, command.verb
        match verb:
            case SayVerb():
                await self.call.writing.write("supervisor.said", wire.SupervisorSaid(by=by, text=verb.text))
                self.live.say(verb.text, allow_interruptions=True)
            case WhisperVerb():
                await self.call.writing.write("supervisor.whispered", wire.SupervisorWhispered(by=by, text=verb.text))
                note = prompt.A_WHISPER.format(text=verb.text)
                await self._note(note)
                if self.call.taken_by is None:
                    self.live.generate_reply(instructions=note)
            case TakeoverVerb():
                await self._take_over(by)
            case ReleaseVerb():
                await self._release(by)
            case EndVerb():
                await self.call.writing.write("supervisor.ended", wire.SupervisorEnded(by=by, reason=verb.reason))
                self.hang_up("supervisor_ended", "supervisor", at_once=True)
            case TransferVerb():
                await self._in_the_room(verb, by=by)

    def _melody_ends(self) -> None:
        self.on_hold = False
        if self.hold is not None:
            self.hold.ended()

    async def _take_over(self, by: Supervisor) -> None:
        if self.call.taken_by is not None:
            raise ValidationError(ALREADY_HELD.format(id=self.call.taken_by.id))
        await self.call.writing.write("supervisor.took_over", wire.SupervisorTookOver(by=by))
        if self.call.waiting_for_a_person:
            await self._answered(wire.AttentionAnswered(ok=True, by=by))
        await self.stop_the_melody()
        await silence(self.live)
        self.call.taken_by = by

    async def _release(self, by: Supervisor) -> None:
        if self.call.taken_by is None:
            raise ValidationError(NOBODY_HOLDS)
        await self.call.writing.write("supervisor.released", wire.SupervisorReleased(by=by))
        hear_again(self.live)
        self.call.taken_by = None
        await self._note(prompt.A_RELEASE)
        self.live.generate_reply(instructions=prompt.A_RELEASE)

    async def _nobody_came(self, wait_s: float) -> None:
        await asyncio.sleep(wait_s)
        failed = NOBODY_TOOK_IT.format(wait_s=wait_s)
        await self._answered(wire.AttentionAnswered(ok=False, by=None, error=failed), waited=True)
        await self.give_the_line_back()

    async def _answered(self, answer: wire.AttentionAnswered, *, waited: bool = False) -> None:
        self.call.waiting_for_a_person = False
        if self.waiting is not None and not waited:
            self.waiting.cancel()
        self.waiting = None
        await self.call.writing.write("attention.answered", answer)

    async def _in_the_room(self, command: WireModel, *, by: Supervisor | None = None) -> None:
        if self.room is None:
            raise Forbidden(NOT_HERE.format(command=type(command).__name__))
        if isinstance(command, TransferVerb | CallTransfer):
            await self._transfer(self.room, CallTransfer(to=command.to, mode=command.mode), by=by)
            return
        await self.room.apply(command)

    # A transfer however it was asked has one outcome entry; a supervisor's is written first,
    # with the mode resolved. A cold one removes the caller, which livekit reads as a hang-up.
    async def _transfer(self, room: CallRoom, wanted: CallTransfer, *, by: Supervisor | None) -> None:
        if by is not None:
            mode = await room.mode_of(wanted)
            await self.call.writing.write(
                "supervisor.transferred", wire.SupervisorTransferred(by=by, to=wanted.to, mode=mode)
            )
            wanted = CallTransfer(to=wanted.to, mode=mode)
        transferred = await room.transfer(wanted, self.live)
        await self.call.writing.write("call.transferred", transferred)
        if not transferred.ok:
            return
        self.ended = ("transferred", "agent")
        if transferred.mode == "warm":
            await silence(self.live)
            room.when_the_person_leaves(f"{telephony.LEG_PREFIX}{wanted.to}", lambda: self.hang_up("transferred"))

    # ── what the agent is handed ──

    def _announce(self, line: str | None) -> None:
        self.agent.announce(line)

    # end_call closes the session as livekit's own initiative, which reads as a drain.
    def _hung_up_by_the_model(self) -> None:
        self.ended = ("agent_hung_up", "agent")

    @contextlib.asynccontextmanager
    async def _music(self) -> AsyncGenerator[None]:
        if self.hold is not None:
            self.hold.began()
        try:
            yield
        finally:
            if self.hold is not None:
                self.hold.ended()

    # The caller is pinned before livekit subscribes, or it links the first seat of a kind it
    # accepts, a supervisor's as soon as a caller's. A written call in a room hears no audio.
    # `record` is said: left unset, livekit asks its cloud; the call's own recorder is ours. A
    # visitor who left may come back (docs/protocol/tokens.md): their call waits, not livekit.
    # `session_host` is said too: left unset, livekit hosts the session for every seat of the room,
    # sending each one the raw turns, the tools' arguments and results, and the prompt on request.
    # A seat reads the call through its log, in its token's projection, and nothing else.
    async def _open(self, history: llm.ChatContext) -> None:
        self.listener.hold = self.hold
        spoken = is_spoken(self.live, self.built)
        options = RoomOptions(
            participant_identity=given_or_unset(self.seat),
            close_on_disconnect=self.call.context.channel is not Channel.web,
            audio_input=NOT_GIVEN if spoken else False,
            audio_output=NOT_GIVEN if spoken else False,
        )
        room = NOT_GIVEN if self.room is None else self.room.room
        self.listener.listen(self.built)
        await self.live.start(self.agent, room=room, room_options=options, record=False, session_host=False)  # pyright: ignore[reportUnknownMemberType]
        echo.cancel(self.live, self.call.context.channel)
        if self.room is not None:
            self.recorder = await recording.record(self.live, self.call.recording, self.room.room, self.room.kind_of)
        given = history.copy()
        given.items[:0] = opening(self.call.context.today, self.built)
        await self.agent.update_chat_ctx(given, exclude_invalid_function_calls=False)

    # A note joins the history as livekit appends: copy, add, update. Never a static block,
    # which would spend the cache.
    async def _note(self, note: str) -> None:
        history = self.agent.chat_ctx.copy()
        history.add_message(role="system", content=note)
        await self.agent.update_chat_ctx(history, exclude_invalid_function_calls=False)

    # Names the state holds (a patient's) join the declared words; livekit replaces the
    # session's keyterms in place.
    def _tell_the_ears(self, state: JsonObject) -> None:
        ears = next((component for component in self.built if isinstance(component, stt.STT)), None)
        if ears is not None and ears.capabilities.keyterms:
            self.live.update_options(keyterms=keyterms(self.call.config, state))

    def _how_it_ended(self) -> tuple[EndReason, EndedBy]:
        if self.ended is not None:
            return self.ended
        closed_for = self.listener.closed_for
        return A_PLATFORM_ERROR if closed_for is None else HOW_IT_ENDED[closed_for]


def given_or_unset[T](value: T | None) -> NotGivenOr[T]:
    """The value, or livekit's NOT_GIVEN when it is None."""
    return NOT_GIVEN if value is None else value


# interrupt() raises when nothing is playing or the session has stopped.
async def silence(live: AgentSession[None]) -> None:
    """Stop the agent's speech now, and keep it from hearing or speaking until it is given back."""
    with contextlib.suppress(RuntimeError):
        await live.interrupt(force=True)
    live.output.set_audio_enabled(False)
    live.input.set_audio_enabled(False)


# The ears first, then the voice, so the agent never speaks before it can hear.
def hear_again(live: AgentSession[None]) -> None:
    """Let the caller's audio reach the ears again after a pause."""
    live.input.set_audio_enabled(True)
    live.output.set_audio_enabled(True)


# The caller is always the far end: on an outbound call that is the `to`. The app cannot read a
# day a golden pinned off the clock, so the entry says it; the persona and what it expects are
# frozen here for the facts and its judge.
def _started(context: CallContext, at: float, worker: str | None, *, medium: Medium) -> wire.CallStarted:
    endpoint = context.route.number or context.route.agent
    from_, to = (endpoint, context.caller) if context.direction is Direction.outbound else (context.caller, endpoint)
    started: JsonObject = {
        "channel": context.channel.value,
        "direction": context.direction.value,
        "from": from_,
        "to": to,
        "run": context.run,
        "persona": context.persona,
        "expects": list(context.expects) or None,
        "caller": None,
        "started_at": at,
        "env": context.env.value,
        "medium": medium.value,
    }
    if worker is not None:
        started["worker"] = worker
    if context.state:
        started["state"] = dict(context.state)
    if context.pinned_day:
        started["today"] = context.pinned_day.isoformat()
    return wire.CallStarted.parse(started, "call.started")
