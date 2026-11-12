"""One job, one call: what it runs on, spoken or typed, the commands it follows, and its end."""

import asyncio
import dataclasses
import logging
import time
from dataclasses import dataclass
from functools import partial
from pathlib import Path

from livekit import api, rtc
from livekit.agents import JobContext, llm
from livekit.agents.voice.background_audio import BackgroundAudioPlayer

from runtime.agents.declaration import Declaration, Greeting, Idle
from runtime.calls.projection import Audience, project_entry, project_state
from runtime.calls.recordings import Recordings, recording_path
from runtime.enums import Channel, Stage
from runtime.exceptions import PinecallError, UpstreamError
from runtime.jobs.service.arrival import Arrived, arrive
from runtime.jobs.service.call_client import CallClient, open_call
from runtime.jobs.service.client import LONGEST_WAIT_S, GatewayClient, Stages
from runtime.jobs.service.ending import end_and_seal, open_writer, release_room
from runtime.jobs.service.hold_clip import find_hold_clip
from runtime.jobs.service.recordings import keep_recording
from runtime.jobs.service.traces import OrgSpans, attributes_of, check_collector
from runtime.kit.loops import survive
from runtime.kit.retry import keep_asking
from runtime.kit.tasks import Tasks
from runtime.kit.text import JsonObject
from runtime.providers.stage import Running
from runtime.session import service as session
from runtime.telephony import service as telephony
from runtime.wire.base import Entry
from runtime.wire.dispatch import Dialling, Dispatch
from runtime.wire.events import CallEnded, ErrorEvent
from runtime.wire.room import CHAT, SCOPE_ATTRIBUTE, TALK
from runtime.wire.state import State
from runtime.wire.worker import HoldAudio, OpenCallResponse

logger = logging.getLogger(__name__)

# How long a chat in a room waits for the person's next message: the voice ceiling's ten minutes.
# A visitor who left the page open held a place for over an hour on 2026-10-03.
A_CHAT_WAITS_S = 600.0
# The talk seat may join after the agent; a session started with nobody seated records nothing.
WAIT_FOR_THE_CALLER_S = 5.0
# A stream of commands that ended is opened again after this: the gateway was told to stop, and
# another takes the call.
A_STREAM_ENDS_S = 0.5
# What a widget is given to read the call's last entry before its room is let go.
A_WIDGET_READS_THE_END_S = 2.0
# One budget for the end of a job, given to livekit as its `session_end_timeout`: the session's
# close (the recording finished, the log flushed in 20 s), the recording's key (13 s) and its
# sealing, the seal (30 s), the writer closed (20 s), the widget and the room. Until 2026-11 four
# constants in four files each sat under a budget of 60 s they exceeded together.
A_JOB_ENDS_WITHIN_S = 150.0

ANSWERED_IN = "the pipeline is live %.2fs after the job arrived"
SESSION_FAILED = "session_failed"
NOT_BUILT = "the session could not be built: {why}"


@dataclass(frozen=True, slots=True)
class JobSettings:
    """What a job reads of its process's settings, taken once as the process is readied."""

    # The agent that answers a job that names none, and the app socket that must serve its calls.
    agent: str | None
    app: str | None
    zone: str
    recordings_root: Path
    voice_lookup_budget_ms: int | None
    text_lookup_budget_ms: int | None
    tool_steps: int | None
    overflow_says: str
    # The worker's name, as its heartbeat says it, and where its jobs tell it their measures.
    worker: str
    measures: Path


# livekit readies a process before a job reaches it and hands it to the job as it is. One object under
# one name: until 2026-11 the gateway's client and the spans were two strings in a dictionary, each
# read back with a check that it was what it should be.
@dataclass(slots=True)
class Warmed:
    """A job's process, readied: its way to the gateway, its spans, where recordings are kept, what it was told."""

    gateway: GatewayClient
    spans: OrgSpans
    recordings: Recordings
    told: JobSettings
    # The call this process runs now: what livekit's end of a session ends.
    job: "Job | None" = None


@dataclass(frozen=True, slots=True)
class Setup:
    """What a call runs on, spoken or typed: its session in its room, and how long it may last and stay quiet."""

    running: session.Session
    room: session.CallRoom
    widget: session.Widget | None
    # What a spoken call says before its greeting: the org's disclosure, and its notice when it records.
    notice: str | None
    # The ceiling of the call in seconds, and the quiet a chat with no ceiling ends after; 0 for none.
    limit_s: int
    quiet_s: float
    idle: Idle | None
    silence_s: int | None


class Job:
    """One call running in this process: its session, the commands it follows, the clocks that watch it, its end."""

    def __init__(self, ctx: JobContext, warmed: Warmed, arrived: Arrived, link: CallClient, setup: Setup) -> None:
        """A call set up and not yet started."""
        self.ctx = ctx
        self.warmed = warmed
        self.arrived = arrived
        self.link = link
        self.setup = setup
        # Read as the call was opened: the same scope, the same canary, the same values under test. A
        # call passed to a teammate reads that agent's stages from then on.
        self.staged_as = arrived.route.agent
        self.tasks = Tasks(f"the job of {link.call}")

    async def start(self) -> None:
        """Start the session, watch the room, follow the app's commands and start the call's clocks."""
        setup, running = self.setup, self.setup.running
        await running.start(notice=setup.notice, worker=self.warmed.told.worker)
        setup.room.watch()
        setup.room.when_the_caller_is_gone(running.caller_hung_up)
        self.tasks.spawn(self.follow())
        self.tasks.spawn(session.keep_time(running, setup.limit_s, exhausted=None))
        self.tasks.spawn(session.end_when_quiet(running, setup.quiet_s))
        self.tasks.spawn(session.watch_the_quiet(running, setup.idle, setup.silence_s))

    # A stream that ends is opened again for as long as the call is not over: the gateway ends it
    # when the call is sealed and when it is told to stop, which is every deploy. Until 2026-11 a
    # stream that ended cleanly was never opened again, and each spoken call whose gateway was
    # released stayed deaf to its app, its supervisor and its caller's hang-up for the rest of it.
    # It is followed until the seal is over, not until the shutdown begins: the app answers
    # `call.ended` with the lines its end hook logs and with call.done, and the seal waits for them.
    # A refusal (a `4xx`) is the gateway's answer and ends the following: asked again, it says the same.
    async def follow(self) -> None:
        """Take the app's commands off the call's stream until the call is over."""
        running, what = self.setup.running, f"the commands of {self.link.call}"
        while not running.over.is_set():
            try:
                await keep_asking(self._listen, within_s=None, what=what, longest_s=LONGEST_WAIT_S)
            except UpstreamError as refused:
                logger.warning("call %s: its app's commands are followed no more: %s", self.link.call, refused)
                return
            await asyncio.sleep(A_STREAM_ENDS_S)

    # A stage its vendor refuses is refused here too: the call goes on with the ones it had.
    async def restage(self, passed_to: str | None) -> None:
        """Read the call's stages again from the gateway and have its session take them."""
        self.staged_as = passed_to or self.staged_as
        arrived, link = self.arrived, self.link
        test = arrived.dispatch.test_values
        staged = await self.warmed.gateway.get_stages(self.staged_as, arrived.scope, call=link.call, test=test)
        now = staged.pipeline
        wanted: dict[Stage, Running] = {Stage.llm: now.llm, Stage.stt: now.stt, Stage.tts: now.tts}
        await session.take_stages(self.setup.running, wanted, alone=now.realtime is not None)
        link.lent.extend(vendor for vendor in now.lent if vendor not in link.lent)

    # livekit runs this alone, after it closed the session of its own and before it leaves the room:
    # the session's close writes `call.ended` and seals, with the room still up, and only then is
    # the room let go. As two shutdown callbacks (until 2026-11) the three ran together, after the
    # room was left: a widget never read the end, and the seal raced the room's deletion.
    async def end(self) -> None:
        """Close the session, which writes the call's end and seals it; then let go of everything else."""
        try:
            await self.setup.running.close()
        finally:
            await self._let_go()

    # A command the session could not apply is said with its call and the next is heard: a follower
    # that ended on one would leave the call deaf to its hang-up and to a supervisor's end. A refusal
    # is the call's own entry, written by its writer like any other.
    async def _listen(self) -> None:
        running = self.setup.running
        async for command in self.link.commands():
            with survive("a command of the app", self.link.call):
                refused = await session.take(running, command, restage=self.restage)
                if refused is not None:
                    running.call.writing.write("error", refused)

    # Each step stands alone: a room that cannot be deleted never keeps the spans from being flushed.
    async def _let_go(self) -> None:
        setup, call = self.setup, self.link.call
        await self.tasks.cancel()
        setup.room.stop()
        if setup.widget is not None:
            with survive("sending a widget the call's end", call):
                await setup.widget.finish(A_WIDGET_READS_THE_END_S)
        with survive("letting go of the room", call):
            await release_room(self.ctx.api, self.ctx.room.name, setup.running.ended)
        # The exporter's flush goes over the network, in the thread it is called from.
        with survive("flushing the org's spans", call):
            await asyncio.to_thread(self.warmed.spans.release)
        with survive("closing the call's socket", call):
            await self.link.aclose()
        self.warmed.job = None


async def answer_job(ctx: JobContext, warmed: Warmed) -> None:
    """Answer the job: find whose call it is, open its log, set it up and start it."""
    began = time.monotonic()
    ctx.log_context_fields = {"room": ctx.job.room.name}
    gateway, told = warmed.gateway, warmed.told
    arrived = await arrive(ctx, gateway, default_agent=told.agent, zone=told.zone)
    if arrived is None:
        return
    route, scope, dispatch, call = arrived.route, arrived.scope, arrived.dispatch, arrived.context.call
    test = dispatch.test_values
    declaration, stages, held = await asyncio.gather(
        gateway.get_agent(route.agent, scope, call=call, test=test),
        gateway.get_stages(route.agent, scope, call=call, test=test),
        gateway.get_hold(route.agent, scope),
    )
    declaration = open_as_dialled(declaration, dispatch)
    link = await open_call(gateway, arrived.open_with(told.app), declaration)
    link.measures, link.lent = told.measures, stages.pipeline.lent
    # An outbound call is its far end answering: nothing is built for a leg that never came up.
    if dispatch.dial is not None and not await _dial_the_far_end(ctx, link, dispatch.dial):
        return
    # Nothing between the open and the start leaves the call open and unsealed: until 2026-11 only a
    # refusal of the session's build was caught, and any other failure left the log to the reaper.
    try:
        warmed.spans.route_to(await check_collector(stages.telemetry, call), attributes_of(arrived.context), call)
        build = set_up_typed if dispatch.scope == CHAT else set_up_spoken
        setup = await build(ctx, warmed, arrived, link, declaration, stages, held)
    except Exception as failed:
        await fail_call(ctx, link, failed)
        if not isinstance(failed, PinecallError):
            raise
        return
    job = warmed.job = Job(ctx, warmed, arrived, link, setup)
    try:
        await job.start()
    except Exception:
        # The session exists: its own end says it, closed and sealed by `end_job` as any call.
        setup.running.hang_up("error", "platform", at_once=True)
        raise
    logger.info(ANSWERED_IN, time.monotonic() - began)


# livekit's `on_session_end`: the one place a job's call ends, whatever ended it.
async def end_job(warmed: Warmed) -> None:
    """End the call this process runs, if it runs one: closed, sealed, its room let go."""
    if warmed.job is not None:
        await warmed.job.end()


# ── what a call runs on ──


async def set_up_spoken(
    ctx: JobContext,
    warmed: Warmed,
    arrived: Arrived,
    link: CallClient,
    declaration: Declaration,
    stages: Stages,
    held: HoldAudio,
) -> Setup:
    """A spoken call set up: recorded if its agent records, its melody, the caller's seat, its three stages built."""
    told, route, context = warmed.told, arrived.route, arrived.context
    audio = recording_path(told.recordings_root, context.call) if declaration.record else None
    if audio is not None:
        link.keep_recording = partial(keep_recording, warmed.recordings, link, route.org, audio)
    call = session.Call(context, declaration, link, audio, _history_of(link))
    room = _room_of(ctx, call, link)
    clip = await find_hold_clip(warmed.gateway, route.agent, arrived.scope, held)
    melody = None if clip is None else session.HoldMusic(clip, ctx.room, BackgroundAudioPlayer(), held.after_s)
    place = session.Place(room, melody, await _seat_of(ctx.room, route.channel))
    running = session.open_spoken(
        call,
        stages.pipeline,
        place,
        lookup_budget_ms=told.voice_lookup_budget_ms,
        tool_steps=told.tool_steps,
        on_ended=lambda reason: ctx.shutdown(reason=reason),
    )
    opened = link.opened
    recording_notice = None if opened is None or audio is None else opened.recording_notice
    said_first = (None if opened is None else opened.disclosure, recording_notice)
    return Setup(
        running=running,
        room=room,
        widget=_widget_of(ctx, call, link, running),
        notice=" ".join(one for one in said_first if one) or None,
        limit_s=_shorter_of(declaration.max_duration_s, opened),
        quiet_s=0,
        idle=declaration.idle,
        silence_s=declaration.silence_timeout_s,
    )


# A written call hears nothing: no recording, no melody, nobody seated, nothing said before the
# greeting, no idle lines. A chat in a room is the one call with no ceiling: it ends after ten
# quiet minutes instead; one with a number keeps its agent's.
async def set_up_typed(
    ctx: JobContext,
    warmed: Warmed,
    arrived: Arrived,
    link: CallClient,
    declaration: Declaration,
    stages: Stages,
    _held: HoldAudio,
) -> Setup:
    """A written call in a room set up: the model alone, and the quiet that ends it."""
    told, route = warmed.told, arrived.route
    call = session.Call(arrived.context, declaration, link, None, _history_of(link))
    room = _room_of(ctx, call, link)
    running = session.open_written(
        call,
        stages.pipeline.llm,
        session.Place(room),
        lookup_budget_ms=told.text_lookup_budget_ms,
        tool_steps=told.tool_steps,
        on_ended=lambda reason: ctx.shutdown(reason=reason),
    )
    has_a_number = route.channel.has_a_number
    return Setup(
        running=running,
        room=room,
        widget=_widget_of(ctx, call, link, running),
        notice=None,
        limit_s=_shorter_of(declaration.max_duration_s if has_a_number else 0, link.opened),
        quiet_s=0 if has_a_number else A_CHAT_WAITS_S,
        idle=None,
        silence_s=None,
    )


# A dialled call may bring its own opening: its words over the agent's greeting, or, with none, what
# the call is for, which the model opens on.
def open_as_dialled(declaration: Declaration, dispatch: Dispatch) -> Declaration:
    """The agent's declaration with the opening its dial asked for."""
    if dispatch.greeting is not None:
        return dataclasses.replace(declaration, greeting=Greeting(say=dispatch.greeting))
    if dispatch.instruction is not None:
        return dataclasses.replace(declaration, greeting=Greeting(reply=dispatch.instruction))
    return declaration


# A call no session runs ends at once, the failure on its log: a Soniox model handed as an argument
# its plugin does not take left a call ringing for the reaper's ten minutes, sealed `drained` with
# nothing of why (2026-11-05).
async def fail_call(ctx: JobContext, link: CallClient, failed: Exception) -> None:
    """End the call that has no session with the failure written on its log, and let the job go."""
    logger.warning("call %s: the session could not be built: %s", link.call, failed)
    writing = open_writer(link)
    writing.write("error", ErrorEvent(code=SESSION_FAILED, message=str(failed), recoverable=False))
    ended = CallEnded(reason="error", ended_by="platform", ended_at=time.time(), duration_s=0.0)
    with survive("sealing a call that has no session", link.call):
        await end_and_seal(link, writing, ended, NOT_BUILT.format(why=failed))
    ctx.shutdown(reason=SESSION_FAILED)


# ── private ──


def _room_of(ctx: JobContext, call: session.Call, link: CallClient) -> session.CallRoom:
    legs = telephony.Legs(trunk=link.trunk, send_on=link.send_on)
    return session.CallRoom(call, ctx.room, ctx.api, legs=legs, claim=link.claim)


# Only the gateway numbers a log, so a widget is sent what is read back from it, projected for the
# public the widget's seat is. Its channel listens before the session starts: what the page says as
# the agent arrives (an event the agent's opening asks for) reaches a listener, not a room that drops it.
def _widget_of(
    ctx: JobContext, call: session.Call, link: CallClient, running: session.Session
) -> session.Widget | None:
    if call.context.channel is not Channel.web:
        return None
    declaration = call.declaration

    async def read_state(viewer: str) -> tuple[JsonObject, int]:
        folded, last_seq = await link.state()
        return project_state(State.model_validate(folded), Audience("public", viewer), declaration), last_seq

    def read_entry(entry: Entry, viewer: str) -> JsonObject | None:
        return project_entry(entry, Audience("public", viewer), declaration)

    reading = session.Reading(state=read_state, since=link.since, tail=link.tail, public=read_entry)
    widget = session.Widget(call, ctx.room, reading)
    widget.when_hung_up(running.caller_hung_up)
    widget.watch()
    return widget


# The turns of the call this one carries on, read back by the gateway from that call's log.
def _history_of(link: CallClient) -> llm.ChatContext | None:
    opened = link.opened
    return session.history_of(opened.history).history if opened is not None and opened.history else None


# The agent's ceiling and what the org's minutes leave, whichever is shorter; 0 for neither.
def _shorter_of(limit_s: int, opened: OpenCallResponse | None) -> int:
    ceiling = 0 if opened is None else opened.seconds_left or 0
    return min(one for one in (limit_s, ceiling) if one) if limit_s or ceiling else 0


# Waiting until answered is what tells busy and no answer apart; the media plane holds the
# ceiling, so a worker that dies does not leave the far end on the line.
async def _dial_the_far_end(ctx: JobContext, link: CallClient, dial: Dialling) -> bool:
    try:
        trunk = await link.leg(dial.to, dial.shown)
        await ctx.api.sip.create_sip_participant(telephony.outbound_leg(ctx.room.name, dial, trunk))
    except (api.TwirpError, UpstreamError) as refused:
        reason = telephony.end_reason_of(refused)
        logger.warning("the far end did not answer: %s", reason)
        ended = CallEnded(reason=reason, ended_by="platform", ended_at=time.time(), duration_s=0.0)
        await end_and_seal(link, open_writer(link), ended, reason)
        ctx.shutdown(reason=reason)
        return False
    return True


# Only the talk seat is the caller: a listener and a supervisor share the room.
async def _seat_of(room: rtc.Room, channel: Channel) -> str | None:
    if channel is Channel.phone:
        leg = await telephony.caller_leg(room, channel)
        return None if leg is None else leg.identity
    if channel is Channel.web:
        return await _talk_seat(room)
    return None


async def _talk_seat(room: rtc.Room) -> str | None:
    seated = _talker_in(room)
    if seated is not None or not room.isconnected():
        return seated
    joined: asyncio.Future[str] = asyncio.get_running_loop().create_future()

    def if_the_caller(seat: rtc.RemoteParticipant) -> None:
        if seat.attributes.get(SCOPE_ATTRIBUTE) == TALK and not joined.done():
            joined.set_result(seat.identity)

    room.on("participant_active", if_the_caller)  # pyright: ignore[reportUnknownMemberType]
    try:
        # Asked again after listening: a join between the two reads would be missed.
        seated = _talker_in(room)
        if seated is not None:
            return seated
        async with asyncio.timeout(WAIT_FOR_THE_CALLER_S):
            return await joined
    except TimeoutError:
        return None
    finally:
        room.off("participant_active", if_the_caller)  # pyright: ignore[reportUnknownMemberType]


def _talker_in(room: rtc.Room) -> str | None:
    seats = room.remote_participants.values()
    return next((seat.identity for seat in seats if seat.attributes.get(SCOPE_ATTRIBUTE) == TALK), None)
