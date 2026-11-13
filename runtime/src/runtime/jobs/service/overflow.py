"""The calls nobody runs: one the fleet had no place for, and one whose worker went away."""

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable

from livekit.agents import JobContext
from livekit.agents.voice import Agent, AgentSession

from runtime.enums import Channel
from runtime.exceptions import UpstreamError
from runtime.jobs.service.arrival import arrive_as_rung
from runtime.jobs.service.call_client import CallClient, open_call
from runtime.jobs.service.ending import end_and_seal, open_writer
from runtime.jobs.service.job import Warmed
from runtime.livekit import close_room
from runtime.providers import service as providers
from runtime.providers.stage import Running, primary_language
from runtime.session import service as session
from runtime.wire.dispatch import Dispatch
from runtime.wire.events import AgentTranscript, CallEnded

logger = logging.getLogger(__name__)

# A room still empty after this is left; otherwise the job waits for the room's own timeout.
A_CALLER_MAY_TAKE_S = 15.0

THE_ONE_SENTENCE = "sp_1"

# What the overflow says where the operator named no sentence of its own (PINECALL_OVERFLOW_SAYS): the
# agent's language when it is one of these, English for any other. Until 2026-11 it was the Spanish one
# for every call, and a caller of an English agent was told the lines were busy in Spanish.
# A call back is promised only to a caller it is asked for, one with a number: a visitor of a page was
# told their number had been noted.
WILL_CALL_BACK = {
    "en": (
        "All our lines are busy right now. We have noted your number and will call you back as soon as "
        "one is free. Thank you for your patience."
    ),
    "es": (
        "En este momento todas nuestras líneas están ocupadas. Hemos tomado nota de su número "
        "y le devolveremos la llamada en cuanto se libere una. Gracias por su paciencia."
    ),
}
ALL_LINES_BUSY = {
    "en": "All our lines are busy right now. Please try again in a few minutes. Thank you for your patience.",
    "es": (
        "En este momento todas nuestras líneas están ocupadas. Por favor, inténtelo de nuevo en unos "
        "minutos. Gracias por su paciencia."
    ),
}

# How a job's call is answered: run (`job.answer_job`), or its caller told the fleet is full.
type Answer = Callable[[JobContext, Warmed], Awaitable[None]]


# Whether the call's worker went away is asked here, once, for the worker's own jobs and for the
# overflow's: until 2026-11 the entrypoint decided it for one and this module for the other.
async def take_job(ctx: JobContext, warmed: Warmed, answer: Answer) -> None:
    """A job of the fleet: its call answered, or, of a call whose worker went away, its caller told."""
    dispatch = Dispatch.parse(ctx.job.metadata)
    if dispatch.worker_gone:
        await tell_the_caller(ctx, warmed, dispatch)
        return
    await answer(ctx, warmed)


# Nobody's ring is sent on from here: the call is answered as it rang, and ended.
async def answer_overflow(ctx: JobContext, warmed: Warmed) -> None:
    """One call the fleet had no place for: one sentence, a call back offered, the room closed."""
    began = time.monotonic()
    ctx.log_context_fields = {"room": ctx.job.room.name}
    gateway = warmed.gateway
    arrived = await arrive_as_rung(ctx, gateway, default_agent=warmed.told.agent, zone=warmed.told.zone)
    route, caller = arrived.route, arrived.arrival.caller
    stages = await gateway.get_stages(route.agent, arrived.scope)
    calls_back = route.channel is Channel.phone and bool(caller)
    says = sentence_in(stages.pipeline.tts.language, warmed.told.overflow_says, calls_back=calls_back)
    link = await open_call(gateway, arrived.open_with(None))
    writing = open_writer(link)
    try:
        await _say_once(ctx, writing, stages.pipeline.tts, says)
        if calls_back and caller:
            await gateway.ask_callback(route.agent, route.channel, caller, link.call)
    finally:
        # Deleting the room is what hangs up a SIP leg.
        await close_room(ctx.api, ctx.room.name)
        length = time.monotonic() - began
        ended = CallEnded(reason="agent_hung_up", ended_by="agent", ended_at=time.time(), duration_s=length)
        await end_and_seal(link, writing, ended, says)


# The gateway ended the call as drained before sending this job, and offered the call back; the
# job's writer takes the call over where the dead worker's stopped. A gateway that no longer
# serves the call refuses the entry and the seal, and its reaper seals it.
async def tell_the_caller(ctx: JobContext, warmed: Warmed, dispatch: Dispatch) -> None:
    """Tell the caller of a call whose worker went away the overflow's sentence, then seal it."""
    call = ctx.job.room.name
    ctx.log_context_fields = {"room": call}
    gateway, scope = warmed.gateway, dispatch.named_scope
    # The gateway offered the call back as it drained the call, to a caller with a number.
    calls_back = dispatch.caller is not None and dispatch.caller.startswith("+")
    says = sentence_in(None, warmed.told.overflow_says, calls_back=calls_back)
    await ctx.connect()
    link = CallClient(gateway, call)
    writing = open_writer(link, after=dispatch.entries_written)
    try:
        if scope is not None and dispatch.agent is not None:
            stages = await gateway.get_stages(dispatch.agent, scope)
            says = sentence_in(stages.pipeline.tts.language, warmed.told.overflow_says, calls_back=calls_back)
            await _say_once(ctx, writing, stages.pipeline.tts, says)
    except UpstreamError:
        logger.warning(
            "call %s: the caller its worker left was not told all of it; the room closes anyway", call, exc_info=True
        )
    finally:
        await close_room(ctx.api, call)
    await writing.close(session.WRITTEN_WITHIN_S)
    try:
        await link.seal([], says)
    except UpstreamError:
        logger.warning("call %s: the gateway did not take the seal; its reaper seals the call", call, exc_info=True)


def sentence_in(language: str | None, operators: str | None, *, calls_back: bool) -> str:
    """The overflow's one sentence: the operator's where it named one, else its own in the agent's language."""
    if operators:
        return operators
    said = WILL_CALL_BACK if calls_back else ALL_LINES_BUSY
    return said.get(primary_language(language) or "en", said["en"])


def sentence_entry(says: str) -> AgentTranscript:
    """The overflow's one sentence as the call's transcript holds it."""
    return AgentTranscript(speech_id=THE_ONE_SENTENCE, text=says, final=True)


async def _say_once(ctx: JobContext, writing: session.Writing, voice: Running, says: str) -> None:
    try:
        async with asyncio.timeout(A_CALLER_MAY_TAKE_S):
            await ctx.wait_for_participant()
    except TimeoutError:
        logger.warning("nobody joined %s in %.0fs: leaving", ctx.room.name, A_CALLER_MAY_TAKE_S)
        return
    speaking: AgentSession[None] = AgentSession(tts=providers.tts_of(voice))
    await speaking.start(Agent(instructions=says), room=ctx.room, record=False, session_host=False)  # pyright: ignore[reportUnknownMemberType]
    await speaking.say(says, allow_interruptions=False)
    writing.write("agent.transcript", sentence_entry(says))
    await speaking.aclose()
