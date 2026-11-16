"""A call whose worker went away, taken up by this one: read from its log, its caller told, gone on with."""

import asyncio
import dataclasses
import logging
import time

from livekit.agents import JobContext

from runtime.calls.context import read_context
from runtime.enums import Medium
from runtime.exceptions import UpstreamError
from runtime.jobs.service.arrival import Arrived
from runtime.jobs.service.call_client import TAKEN_UP, CallClient
from runtime.jobs.service.job import Job, Setup, Warmed, set_up_spoken, set_up_typed
from runtime.jobs.service.overflow import tell_the_caller
from runtime.jobs.service.traces import attributes_of, check_collector
from runtime.providers.stage import primary_language
from runtime.session import service as session
from runtime.telephony import service as telephony
from runtime.wire.dispatch import Dispatch
from runtime.wire.worker import OpenCallResponse, TakenUpResponse

logger = logging.getLogger(__name__)

# What the caller hears first from the worker that takes their call up: they sat through a silence
# they cannot explain, so they are told it was ours and that the call goes on. Then the agent answers
# what they said last, if the loss cut its reply.
STAY_ON_THE_LINE = {
    "en": (
        "We are sorry, there was a technical problem on our side. Please stay on the line, "
        "we are picking up right where we left off."
    ),
    "es": (
        "Disculpe, hubo un problema técnico de nuestro lado. Por favor, permanezca en la línea, "
        "seguimos donde habíamos quedado."
    ),
}


# The gateway is asked before the room is joined: it answers only while the caller is alone in it, so
# two workers offered the same call never both speak. Its refusals are two. `410`: a worker is on the
# call already or its caller left, and this job leaves the room as it is. Anything else: the call
# cannot be gone on with (it never started, or it ended as its worker went), and its caller is told
# the overflow's sentence, as a call no worker has a seat for is.
async def take_up_job(ctx: JobContext, warmed: Warmed, dispatch: Dispatch) -> None:
    """Take up the call of a worker that went away: the same call, on what its log holds, its caller told first."""
    began, call = time.monotonic(), ctx.job.room.name
    ctx.log_context_fields = {"room": call}
    try:
        taken = await warmed.gateway.take_up(call)
    except UpstreamError as refused:
        if refused.answered == TAKEN_UP:
            logger.info("call %s is not this worker's to take up: %s", call, refused)
            ctx.shutdown(reason="not taken up")
            return
        logger.warning("call %s cannot be taken up, so its caller is told: %s", call, refused)
        await tell_the_caller(ctx, warmed, dispatch)
        return
    try:
        job = await _set_up(ctx, warmed, dispatch, taken)
    except Exception:
        logger.warning("call %s: no session could be built to take it up, so its caller is told", call, exc_info=True)
        await tell_the_caller(ctx, warmed, dispatch, taken)
        return
    warmed.job = job
    try:
        resumption = dataclasses.replace(session.history_of(taken.history), started_at=taken.started_at)
        await job.take_up(resumption, _sentence_in(job.setup.running.call.declaration.language))
    except Exception:
        # The session exists: its own end says it, closed and sealed by `end_job` as any call.
        job.setup.running.hang_up("error", "platform", at_once=True)
        raise
    took = time.monotonic() - began
    logger.info("call %s taken up %.2fs after the job arrived, %d entries in", call, took, taken.written)


# The call as it was opened, read from what the gateway kept of it and never from the room again: the
# number it rang, its contact, its state and the call it continues are the first worker's word.
async def _set_up(ctx: JobContext, warmed: Warmed, dispatch: Dispatch, taken: TakenUpResponse) -> Job:
    gateway, told = warmed.gateway, warmed.told
    context = read_context(taken.opening.context.model_dump(mode="json"))
    route = context.route
    arrival = telephony.Arrival(context.caller, context.channel, context.direction, route.number)
    arrived = Arrived(dispatch, arrival, route, context)
    call, scope = context.call, arrived.scope
    _, declaration, stages, held = await asyncio.gather(
        ctx.connect(),
        gateway.get_agent(route.agent, scope, call=call),
        gateway.get_stages(route.agent, scope, call=call),
        gateway.get_hold(route.agent, scope),
    )
    link = CallClient(gateway, call, taken.opening, OpenCallResponse(seconds_left=None, minutes=None), declaration)
    link.measures, link.lent = told.measures, stages.pipeline.lent
    link.written, link.taken_up = taken.written, taken.taken_up
    warmed.spans.route_to(await check_collector(stages.telemetry, call), attributes_of(context), call)
    build = set_up_typed if taken.medium is Medium.text else set_up_spoken
    setup = await build(ctx, warmed, arrived, link, declaration, stages, held)
    return Job(ctx, warmed, arrived, link, _with_what_is_left(setup, taken.started_at))


# The call's ceiling ran while its first worker held it: what is left of it is this worker's.
def _with_what_is_left(setup: Setup, started_at: float) -> Setup:
    if not setup.limit_s:
        return setup
    return dataclasses.replace(setup, limit_s=max(1, setup.limit_s - int(time.time() - started_at)))


def _sentence_in(language: str | None) -> str:
    return STAY_ON_THE_LINE.get(primary_language(language) or "en", STAY_ON_THE_LINE["en"])
