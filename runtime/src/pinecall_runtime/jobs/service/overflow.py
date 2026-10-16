"""The calls nobody runs: one the fleet had no seat for, and one whose worker went away."""

import asyncio
import logging
import time

from livekit.agents import JobContext
from livekit.agents.voice import Agent, AgentSession

from pinecall_runtime.calls import service as calls
from pinecall_runtime.channels import service as channels
from pinecall_runtime.config import Settings
from pinecall_runtime.enums import Channel
from pinecall_runtime.exceptions import GatewayUnavailable
from pinecall_runtime.fleet import service as fleet
from pinecall_runtime.jobs.service.client import GatewayClient
from pinecall_runtime.jobs.service.ending import end_and_seal, open_writer
from pinecall_runtime.jobs.service.job import context_of, pipeline_of
from pinecall_runtime.kit.auth import Scope
from pinecall_runtime.providers import service as providers
from pinecall_runtime.session import service as session
from pinecall_runtime.telephony import service as telephony
from pinecall_runtime.wire.dispatch import Dispatch
from pinecall_runtime.wire.events import AgentTranscript, CallEnded

logger = logging.getLogger(__name__)

# A room still empty after this is left; otherwise the job waits for the room's own timeout.
A_CALLER_MAY_TAKE_S = 15.0

THE_ONE_SENTENCE = "sp_1"
NOT_TOLD = "call %s: the caller its worker left was not told all of it; the room closes anyway"
NOT_SEALED = "call %s: the gateway did not take the seal; its reaper seals the call"


async def answer_overflow(ctx: JobContext, gateway: GatewayClient, settings: Settings) -> None:
    """One call the fleet had no seat for: one sentence, a call back offered, the room closed."""
    began = time.monotonic()
    ctx.log_context_fields = {"room": ctx.job.room.name}
    dispatch = Dispatch.parse(ctx.job.metadata)
    if dispatch.worker_gone:
        await tell_the_caller(ctx, gateway, settings, dispatch)
        return
    await ctx.connect()
    arrival = await telephony.arrival_of(dispatch, ctx.room)
    number = arrival.number if dispatch.org is None else None
    found = await gateway.routes(dispatch.named_scope, number=number, channel=arrival.channel)
    route = channels.resolve_route(dispatch, arrival, found, settings.agent)
    scope = Scope(route.org, route.env, dispatch.holder or "")
    stages = pipeline_of(await gateway.stages(route.agent, scope))
    context = context_of(ctx, dispatch, arrival, route, settings)
    await gateway.open(
        calls.OpenCallRequest(agent=route.agent, context=context, carrier_account=arrival.carrier_account)
    )
    writing = open_writer(gateway, context.call)
    try:
        await _say_once(ctx, writing, stages.tts, settings.overflow_says)
        if route.channel is Channel.phone and arrival.caller:
            wanted = calls.CallbackRequest(
                agent=route.agent, channel=route.channel, number=arrival.caller, call=context.call
            )
            await gateway.callback(wanted)
    finally:
        # Deleting the room is what hangs up a SIP phone_leg.
        await fleet.close_room(ctx.api, ctx.room.name)
        ended = CallEnded(
            reason="agent_hung_up", ended_by="agent", ended_at=time.time(), duration_s=time.monotonic() - began
        )
        await end_and_seal(gateway, writing, ended, settings.overflow_says)


# The gateway ended the call as drained before sending this job, and offered the call back; the
# job's writer takes the call over where the dead worker's stopped. A gateway that no longer
# serves the call refuses the entry and the seal, and its reaper seals it.
async def tell_the_caller(ctx: JobContext, gateway: GatewayClient, settings: Settings, dispatch: Dispatch) -> None:
    """Tell the caller of a call whose worker went away the overflow's sentence, then seal it."""
    call = ctx.job.room.name
    ctx.log_context_fields = {"room": call}
    scope = dispatch.named_scope
    await ctx.connect()
    says = settings.overflow_says
    writing = open_writer(gateway, call, after=dispatch.entries_written)
    try:
        if scope is not None and dispatch.agent is not None:
            stages = pipeline_of(await gateway.stages(dispatch.agent, scope))
            await _say_once(ctx, writing, stages.tts, says)
    except GatewayUnavailable:
        logger.warning(NOT_TOLD, call, exc_info=True)
    finally:
        await fleet.close_room(ctx.api, call)
    await writing.close(session.WRITTEN_WITHIN_S)
    try:
        await gateway.sealed(call, calls.SealCallRequest(usage=[], outcome=says))
    except GatewayUnavailable:
        logger.warning(NOT_SEALED, call, exc_info=True)


def sentence_entry(says: str) -> AgentTranscript:
    """The overflow's one sentence as the call's transcript holds it."""
    return AgentTranscript(speech_id=THE_ONE_SENTENCE, text=says, final=True)


async def _say_once(ctx: JobContext, writing: session.Writing, voice: providers.Running, says: str) -> None:
    try:
        async with asyncio.timeout(A_CALLER_MAY_TAKE_S):
            await ctx.wait_for_participant()
    except TimeoutError:
        logger.warning("nobody joined %s in %.0fs: leaving", ctx.room.name, A_CALLER_MAY_TAKE_S)
        return
    speaking: AgentSession[None] = AgentSession(tts=providers.tts_of(voice))
    await speaking.start(Agent(instructions=says), room=ctx.room, record=False)  # pyright: ignore[reportUnknownMemberType]
    await speaking.say(says, allow_interruptions=False)
    writing.write("agent.transcript", sentence_entry(says))
    await speaking.aclose()
