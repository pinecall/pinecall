"""One job, one call: whose it is, what it runs on, the room it runs in, and its end."""

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable, Coroutine
from functools import partial
from pathlib import Path

from livekit import api
from livekit.agents import JobContext, JobProcess, llm

from pinecall_runtime.agents import service as agents
from pinecall_runtime.calls import service as calls
from pinecall_runtime.calls.context import CallContext, Contact, Route
from pinecall_runtime.channels import service as channels
from pinecall_runtime.compliance import service as compliance
from pinecall_runtime.config import Settings
from pinecall_runtime.enums import Channel, Env
from pinecall_runtime.exceptions import GatewayUnavailable, PinecallError
from pinecall_runtime.jobs.service.client import GatewayClient
from pinecall_runtime.jobs.service.ending import end_and_seal, open_writer, release_room
from pinecall_runtime.jobs.service.heartbeat import worker_name_of
from pinecall_runtime.jobs.service.measures import measures_path, report_batch
from pinecall_runtime.jobs.service.recorder import has_audio, store_recording
from pinecall_runtime.jobs.service.room import hold_music_for, seat_of, widget_for
from pinecall_runtime.jobs.service.stream import again
from pinecall_runtime.jobs.service.traces import OrgSpans, attributes_of
from pinecall_runtime.kit.auth import Scope
from pinecall_runtime.kit.loops import survived
from pinecall_runtime.kit.text import JsonObject
from pinecall_runtime.kit.time import today_in
from pinecall_runtime.providers import service as providers
from pinecall_runtime.session import service as session
from pinecall_runtime.telephony import service as telephony
from pinecall_runtime.wire.base import BatchedEntry, Command, Entry
from pinecall_runtime.wire.commands import command_of
from pinecall_runtime.wire.dispatch import Dialling, Dispatch
from pinecall_runtime.wire.events import CallEnded, ErrorEvent, ToolCall
from pinecall_runtime.wire.metrics import ModelUsage
from pinecall_runtime.wire.parts import PlatformTool, ToolResult

logger = logging.getLogger(__name__)

# The one scope that makes a visit written: a chat in the widget, no microphone.
WRITTEN_SCOPE = "chat"

# How long a chat in a room waits for the person's next message: the voice ceiling's ten minutes.
# A visitor who left the page open held a seat for over an hour on 2026-10-03.
A_CHAT_WAITS_S = 600.0

ANSWERED_IN = "the pipeline is live %.2fs after the job arrived"


async def answer_job(ctx: JobContext, gateway: GatewayClient, settings: Settings) -> None:
    """Answer the job: join, find whose call it is, open its log, and run it until it ends."""
    began = time.monotonic()
    ctx.log_context_fields = {"room": ctx.job.room.name}
    dispatch = Dispatch.parse(ctx.job.metadata)
    named = dispatch.named_scope
    # The org's routes are fetched while the room connects; the dialled number waits for it.
    _, found = await asyncio.gather(ctx.connect(), gateway.routes(named, number=None, channel=Channel.phone))
    arrival = await telephony.arrival_of(dispatch, ctx.room)
    if arrival.number is not None and named is None:
        found = await gateway.routes(None, number=arrival.number, channel=arrival.channel)
    route = channels.resolve_route(dispatch, arrival, found, settings.agent)
    if telephony.may_be_a_developers(dispatch, arrival, route) and await _hand_over(
        ctx, gateway, dispatch, arrival, route
    ):
        return
    scope = Scope(route.org, route.env, dispatch.holder or "")
    context = context_of(ctx, dispatch, arrival, route, settings)
    config, keys, played = await asyncio.gather(
        gateway.agent(route.agent, scope, call=context.call, test=dispatch.tuning),
        gateway.stages(route.agent, scope, call=context.call, test=dispatch.tuning),
        gateway.hold_audio(route.agent, scope),
    )
    opened = await gateway.open(
        calls.OpenCallRequest(
            agent=route.agent,
            context=context,
            app=dispatch.app or settings.app,
            carrier_account=arrival.carrier_account,
        )
    )
    # An outbound call is its far end answering: nothing is built for a phone_leg that never came up.
    if dispatch.dial is not None and not await _far_end_answers(ctx, gateway, context, dispatch.dial):
        return
    typed = dispatch.scope == WRITTEN_SCOPE
    audio = _recording_path(config, settings, context.call, typed=typed)
    pipeline = pipeline_of(keys)
    spans = _route_spans(ctx.proc, telemetry_of(keys), context)

    # The session closed its recorder before it seals: the seal points at a whole file.
    async def seal(usage: list[ModelUsage], outcome: str) -> None:
        recording = await _keep_recording(audio, partial(store_recording, settings, gateway, route.org, context.call))
        sealing = calls.SealCallRequest(usage=usage, outcome=outcome, recording=recording, lent=pipeline.lent)
        await gateway.sealed(context.call, sealing)

    platform = _platform_of(gateway, context.call, config, seal, measures_path(settings))
    call = session.Call(context, config, platform, audio, _carried_history(opened))
    running = (
        session.text_session(call, pipeline.llm, settings.text_lookup_budget_ms)
        if typed
        else session.voice_session(call, pipeline, settings.voice_lookup_budget_ms)
    )

    # Registered before anything else can fail: a call that dies in its setup still seals.
    # livekit reads a shutdown callback's `__code__`, which a `partial` has not. The stream of the
    # app's commands is followed until the seal is over, not until the shutdown begins (livekit runs
    # the callbacks at once, together): the app answers `call.ended` with the lines its end hook
    # logs and with call.done, and the seal waits for them.
    following: list[asyncio.Task[None]] = []

    async def close(_reason: str) -> None:
        await running.close()
        for task in following:
            task.cancel()
        spans.release()

    ctx.add_shutdown_callback(close)
    room = session.CallRoom(
        call,
        ctx.room,
        ctx.api,
        legs=telephony.Legs(trunk=partial(_trunk_for, gateway, context), sent_on=partial(_sent_on, gateway, context)),
        claim=partial(_claim, gateway, context.call),
    )
    hold = await hold_music_for(gateway, route.agent, scope, played, typed=typed)
    await running.start(
        room=room,
        hold=hold,
        seat=await seat_of(ctx.room, route.channel, typed=typed),
        notice=None if typed else notice_of(opened, recorded=audio is not None),
        worker=worker_name_of(settings),
    )
    if hold is not None:
        await hold.start(ctx.room)
    room.watch()

    # A call the session ended already (a transfer, the model's goodbye) is not ended again.
    def caller_gone() -> None:
        if running.ended is None:
            running.hang_up("caller_hung_up", "caller")

    room.when_the_caller_is_gone(caller_gone)
    widget = widget_for(gateway, call, ctx.room, caller_gone) if route.channel is Channel.web else None
    logger.info(ANSWERED_IN, time.monotonic() - began)
    following.append(asyncio.create_task(_follow_commands(gateway, running, context.call, caller_gone)))
    timer = asyncio.create_task(
        session.keep_time(running, _limit_of(config, opened, route, typed=typed), exhausted=None)
    )
    # A chat in a room is the one call with no ceiling: it ends after ten quiet minutes instead.
    quiet = typed and not route.channel.has_a_number
    silence = asyncio.create_task(session.end_when_quiet(running, A_CHAT_WAITS_S if quiet else 0))
    ctx.add_shutdown_callback(_let_go(ctx, running, room, widget, timer, silence))


def context_of(
    ctx: JobContext, dispatch: Dispatch, arrival: channels.Arrival, route: Route, settings: Settings
) -> CallContext:
    """The call as the gateway opens it, from the job, its dispatch and its route."""
    return CallContext(
        # The room is the call: its name is the id the gateway minted, or the SIP rule's.
        call=ctx.room.name or ctx.job.id,
        channel=route.channel,
        direction=arrival.direction,
        caller=arrival.caller,
        route=route,
        today=today_in(settings.timezone),
        contact=None if dispatch.contact is None else Contact(id=dispatch.contact),
        metadata=dispatch.metadata,
        run=dispatch.run,
        persona=dispatch.persona,
        expects=tuple(dispatch.expects),
        holder=dispatch.holder,
        state=dispatch.state,
        continues=dispatch.continues,
    )


# The org's sentences said before the greeting: the disclosure, then the notice when it records.
def notice_of(opened: calls.OpenCallResponse, *, recorded: bool) -> str | None:
    """What a spoken call says before its greeting, or None."""
    recording = opened.recording_notice if recorded else None
    return " ".join(item for item in (opened.disclosure, recording) if item) or None


def pipeline_of(keys: agents.PipelineKeys) -> providers.Pipeline:
    """The stages as the session builds them, from the gateway's answer."""
    return providers.Pipeline(
        llm=_running(keys.llm),
        stt=_running(keys.stt),
        tts=_running(keys.tts),
        realtime=None if keys.realtime is None else _running(keys.realtime),
    )


def telemetry_of(keys: agents.PipelineKeys) -> compliance.Telemetry | None:
    """The org's own collector for the call's spans; None when its traces go nowhere."""
    target = keys.telemetry
    return (
        None
        if target is None
        else compliance.Telemetry(endpoint=target.endpoint, headers=target.headers, pii=target.pii)
    )


# The refusal is the call's own entry, written by its writer like any other.
async def follow_command(running: session.Session, command: Command, caller_gone: Callable[[], None]) -> None:
    """One command on the call's stream: the caller's own hang-up, or one of the app's."""
    if command.type == calls.CALLER_HUNG_UP:
        caller_gone()
        return
    await apply_command(running, command)


async def apply_command(running: session.Session, command: Command) -> None:
    """Apply one of the app's commands; a refusal is an `error` entry on the call."""
    try:
        await running.apply(command_of(command))
    except PinecallError as refused:
        error = ErrorEvent(code="refused", message=str(refused), command=command.type, id=command.id, recoverable=True)
        running.call.writing.write("error", error)


# The caller and their carrier stay where they are: production's LiveKit holds their phone_leg.
async def _hand_over(
    ctx: JobContext, gateway: GatewayClient, dispatch: Dispatch, arrival: channels.Arrival, route: Route
) -> bool:
    try:
        handed = await gateway.rings_for(route.agent, route.org, arrival.caller)
    except GatewayUnavailable:
        logger.warning("could not ask whose phone rings %s: the call stays here", route.agent)
        return False
    if handed.holder is None or handed.fleet is None:
        return False
    moved = dispatch.model_copy(
        update={
            "agent": route.agent,
            "org": route.org,
            "env": Env.sandbox,
            "holder": handed.holder,
            "caller": arrival.caller,
            "diverted_from": Env.production,
        }
    )
    if not await telephony.handed_on(ctx.api, ctx.room.name, handed=handed, moved=moved, number=str(route.number)):
        return False
    ctx.shutdown(reason=f"handed to {handed.fleet}")
    return True


def _recording_path(config: agents.AgentConfig, settings: Settings, call: str, *, typed: bool) -> Path | None:
    if typed or not config.record:
        return None
    return calls.recording_path(Path(settings.recordings_root), call)


# The agent's ceiling on a call with a number or a spoken one, and what the org's minutes leave.
def _limit_of(config: agents.AgentConfig, opened: calls.OpenCallResponse, route: Route, *, typed: bool) -> int:
    limit = config.max_duration_s if route.channel.has_a_number or not typed else 0
    ceiling = opened.seconds_left or 0
    return min(item for item in (limit, ceiling) if item) if limit or ceiling else 0


# What the call writes also tells its worker's heartbeat: first audio, errors, how it ended.
def _platform_of(
    gateway: GatewayClient, call: str, config: agents.AgentConfig, seal: session.Seal, measures: Path
) -> session.Platform:
    async def append_many(entries: list[BatchedEntry], *, after: int) -> list[Entry]:
        report_batch(measures, entries)
        return await gateway.append_many(call, entries, after=after)

    async def tool(use: session.ToolUse, speech: str | None) -> ToolResult:
        spec = config.tools_by_name.get(use.name)
        called = ToolCall(call_id=use.call_id, name=use.name, arguments=use.arguments, speech_id=speech)
        return await gateway.tool(call, config.slug, called.dump(), 30.0 if spec is None else spec.timeout_s)

    async def lookup(tool_name: PlatformTool, arguments: JsonObject, speech: str | None) -> JsonObject:
        return await gateway.lookup(call, tool_name, arguments, speech)

    async def done() -> None:
        await gateway.done(call)

    return session.Platform(append_many=append_many, tool=tool, lookup=lookup, seal=seal, done=done)


# A recording the worker could not seal is dropped (recorder.py): the seal names none.
async def _keep_recording(audio: Path | None, store: Callable[[Path], Awaitable[Path | None]]) -> str | None:
    if audio is None or not await asyncio.to_thread(has_audio, audio):
        return None
    stored = await store(audio)
    return None if stored is None else str(stored)


# The platform wants a claim that answers nothing; the client's says whether a page was waiting.
async def _claim(gateway: GatewayClient, call: str, code: str) -> None:
    await gateway.claim(call, code)


async def _trunk_for(gateway: GatewayClient, context: CallContext, to: str) -> telephony.Trunk:
    route = context.route
    scope = Scope(route.org, route.env, context.holder or "")
    trunk = await gateway.leg(route.agent, scope, to=to, call=context.call, shown=route.number)
    return telephony.Trunk(config=telephony.sip_config(trunk), shown=trunk.shown)


async def _sent_on(gateway: GatewayClient, context: CallContext, to: str) -> None:
    route = context.route
    await gateway.sent_on(route.agent, Scope(route.org, route.env, context.holder or ""), to=to, call=context.call)


# Waiting until answered is what tells busy and no answer apart; the media plane holds the
# ceiling, so a worker that dies does not leave the far end on the line.
async def _far_end_answers(ctx: JobContext, gateway: GatewayClient, context: CallContext, dial: Dialling) -> bool:
    route = context.route
    scope = Scope(route.org, route.env, context.holder or "")
    try:
        trunk = await gateway.leg(route.agent, scope, to=dial.to, call=context.call, shown=dial.shown)
        await ctx.api.sip.create_sip_participant(telephony.outbound_leg(ctx.room.name, dial, trunk))
    except (api.TwirpError, GatewayUnavailable) as refused:
        reason = telephony.end_reason_of(refused)
        logger.warning("the far end did not answer: %s", reason)
        ended = CallEnded(reason=reason, ended_by="platform", ended_at=time.time(), duration_s=0.0)
        await end_and_seal(gateway, open_writer(gateway, context.call), ended, reason)
        ctx.shutdown(reason=reason)
        return False
    return True


# The turns of the call this one carries on, read back by the gateway from that call's log.
def _carried_history(opened: calls.OpenCallResponse) -> llm.ChatContext | None:
    return session.taken_up(opened.history).history if opened.history else None


# A stream that ends means the gateway went away: it is opened again; a 4xx ends it.
async def _follow_commands(
    gateway: GatewayClient, running: session.Session, call: str, caller_gone: Callable[[], None]
) -> None:
    # A command the session could not apply is said with its call and the next is heard: a follower
    # that ended on one would leave the call deaf to its hang-up and to a supervisor's end.
    async def listen() -> None:
        async for command in gateway.commands(call):
            with survived("a command of the app", call):
                await follow_command(running, command, caller_gone)

    await again(listen, None, f"the commands of {call}")


# A closure, not a partial: livekit reads a shutdown callback's `__code__`.
def _let_go(
    ctx: JobContext,
    running: session.Session,
    room: session.CallRoom,
    widget: session.Widget | None,
    *tasks: asyncio.Task[None],
) -> Callable[[str], Coroutine[None, None, None]]:
    async def let_go(_reason: str) -> None:
        for task in tasks:
            task.cancel()
        room.stop()
        if widget is not None:
            widget.stop()
        await release_room(ctx.api, ctx.room.name, running.ended)

    return let_go


# The process's router of spans, warmed with it (worker.py); a process warmed by nobody routes
# into the void. Every span of the job names the call, whoever reads it.
def _route_spans(proc: JobProcess, telemetry: compliance.Telemetry | None, context: CallContext) -> OrgSpans:
    found = proc.userdata.get("spans")
    spans = found if isinstance(found, OrgSpans) else OrgSpans()
    spans.route_to(telemetry, attributes_of(context), context.call)
    return spans


def _running(stage: agents.RunningStage) -> providers.Running:
    return providers.Running(
        vendor=stage.vendor,
        credentials=stage.credentials,
        model=stage.model,
        builds=stage.builds,
        options=stage.options,
        voice=stage.voice,
        language=stage.language,
        hints=tuple(stage.hints),
        ends_the_turn=stage.ends_the_turn,
        turn_model=stage.turn_model,
        request=stage.request,
        lent=stage.lent,
        fallbacks=tuple(_running(fallback) for fallback in stage.fallbacks),
    )
