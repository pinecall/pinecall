"""A call whose worker went away mid-call: its caller told once, a call back offered, drained."""

import logging

from livekit.protocol.models import DisconnectReason, ParticipantInfo
from livekit.protocol.webhook import WebhookEvent
from sqlalchemy.ext.asyncio import AsyncSession

from pinecall_runtime.calls.repository.facts import FactsRepository
from pinecall_runtime.calls.repository.heads import CallHead, HeadRepository
from pinecall_runtime.calls.service.serving import Serving
from pinecall_runtime.enums import Channel, Env
from pinecall_runtime.fleet import service as fleet
from pinecall_runtime.wire.dispatch import Dispatch
from pinecall_runtime.wire.events import CallbackRequested, CallEnded

logger = logging.getLogger(__name__)

LEFT = "participant_left"

# The reasons livekit gives when a participant's connection was lost rather than closed: a worker
# killed, a machine gone, a job process that died. A worker that ends a call, drains or hands it
# on leaves CLIENT_INITIATED; a room deleted says so. livekit-server pkg/rtc/types ToDisconnectReason.
LOST = frozenset(
    {
        DisconnectReason.SIGNAL_CLOSE,
        DisconnectReason.CONNECTION_TIMEOUT,
        DisconnectReason.STATE_MISMATCH,
        DisconnectReason.JOIN_FAILURE,
        DisconnectReason.MEDIA_FAILURE,
        DisconnectReason.AGENT_ERROR,
    }
)

CALLBACK = "callback.requested"


# The end is written first and only once: it is what tells a second delivery of the same event,
# the worker's own late end and the told job's own leaving that there is nothing left to do. The
# room is asked of the LiveKit of the env that sent the event.
async def stranded(
    session: AsyncSession, serving: Serving, offering: fleet.Offering, env: Env, event: WebhookEvent
) -> str | None:
    """End the call whose agent the event says was lost, and send its fleet to tell the caller."""
    server = offering.servers[env]
    if not _an_agent_lost(event):
        return None
    call = event.room.name
    kept = await HeadRepository(session).head_of_call(call)
    if kept is None or kept.sealed or kept.scope is None:
        return None
    if not await fleet.left_alone(server, call):
        return None
    if not await _end(serving, call, kept):
        return None
    await _offer_a_call_back(session, serving, call, kept.agent)
    scope = kept.scope
    dispatch = Dispatch(
        agent=kept.agent,
        org=scope.org,
        env=scope.env,
        holder=scope.holder or None,
        worker_gone=True,
        entries_written=kept.written,
    )
    await offering.offer(call, await fleet.fleet_of_env(session, scope.env), dispatch)
    reason = DisconnectReason.Name(event.participant.disconnect_reason)
    logger.warning(
        "call %s: its worker went away (%s); the caller is told once and the call ends drained", call, reason
    )
    return call


def _an_agent_lost(event: WebhookEvent) -> bool:
    return (
        event.event == LEFT
        and event.participant.kind == ParticipantInfo.Kind.AGENT
        and event.participant.disconnect_reason in LOST
        and bool(event.room.name)
    )


# A log this process does not serve (it restarted since the call opened) is written and let go,
# as the reaper does: the told job's own entries then find no call here, and the reaper seals it.
async def _end(serving: Serving, call: str, kept: CallHead) -> bool:
    now = serving.logs.store.clock()
    started = now if kept.started_at is None else kept.started_at
    ended = CallEnded(reason="drained", ended_by="platform", ended_at=now, duration_s=max(now - started, 0.0))
    served = serving.live.calls.get(call)
    if served is not None:
        return await served.log.append_first("call.ended", ended.dump()) is not None
    log = serving.logs.writing(call, kept.agent)
    try:
        return await log.append_first("call.ended", ended.dump()) is not None
    finally:
        serving.logs.forget(call)


# Only a phone has a number to call back: the caller's, or on an outbound call the one dialled.
async def _offer_a_call_back(session: AsyncSession, serving: Serving, call: str, agent: str) -> None:
    facts = await FactsRepository(session).get(call)
    if facts is None or facts.channel != "phone":
        return
    number = facts.from_number if facts.direction == "inbound" else facts.to_number
    if not number:
        return
    wanted = CallbackRequested(channel=Channel.phone, number=number, via="overflow", call=call, contact=None)
    await serving.logs.agent(agent).append(CALLBACK, wanted.dump())
