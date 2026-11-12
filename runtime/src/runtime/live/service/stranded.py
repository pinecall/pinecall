"""A room event LiveKit signed: a call whose worker went away told and ended, a caller alone offered a worker."""

import logging

from livekit.protocol.models import DisconnectReason, ParticipantInfo
from livekit.protocol.webhook import WebhookEvent
from sqlalchemy.ext.asyncio import AsyncSession

from runtime.calls import service as calls
from runtime.enums import Channel, Direction, Env
from runtime.fleet import service as fleet
from runtime.live.parts import LiveParts
from runtime.livekit import is_left_alone
from runtime.telephony import service as telephony
from runtime.wire.dispatch import Dispatch
from runtime.wire.events import CallbackRequested, CallEnded

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


# livekit sends every room event of the box: all but an agent lost mid-call are answered and let be.
# Each env's LiveKit names its env in the URL its config sends to, so the room is asked of the LiveKit
# it lives on. In this order: a worker gone sends the sentence, a caller alone is offered a worker, a
# room an agent joined or that ended is let go, and a room a hand-over bridges goes with either of
# its legs; each event moves one of the four.
async def hear_room_event(session: AsyncSession, live: LiveParts, env: Env, event: WebhookEvent) -> None:
    """One room event of an env's LiveKit: an agent lost is told, a caller alone is offered a worker."""
    server = live.servers[env]
    await end_stranded(session, live, env, event)
    await fleet.offer_arrival(live.offering, server, event)
    await fleet.forget_settled(live.offering, event)
    await telephony.unbridge(server, event)


# The end is written first and only once: it is what tells a second delivery of the same event,
# the worker's own late end and the told job's own leaving that there is nothing left to do. The
# room is asked of the LiveKit of the env that sent the event.
#
# This writes the call's end and does not seal it: the job sent to tell the caller still writes to
# the log, and a sealed log would refuse it. The reaper ends the call by the one end every call has.
async def end_stranded(session: AsyncSession, live: LiveParts, env: Env, event: WebhookEvent) -> str | None:
    """End the call whose agent the event says was lost, and send its fleet to tell the caller."""
    if not _tells_of_an_agent_lost(event):
        return None
    call = event.room.name
    kept = await calls.find_head(session, call)
    if kept is None or kept.sealed or kept.scope is None:
        return None
    if not await is_left_alone(live.servers[env], call):
        return None
    if not await _end(live, call, kept):
        return None
    await _offer_a_call_back(session, live, call, kept.agent)
    scope = kept.scope
    dispatch = Dispatch(
        agent=kept.agent,
        org=scope.org,
        env=scope.env,
        holder=scope.holder or None,
        worker_gone=True,
        entries_written=kept.written,
    )
    await live.offering.offer(call, await fleet.fleet_of_env(session, scope.env), dispatch)
    reason = DisconnectReason.Name(event.participant.disconnect_reason)
    logger.warning(
        "call %s: its worker went away (%s); the caller is told once and the call ends drained", call, reason
    )
    return call


def _tells_of_an_agent_lost(event: WebhookEvent) -> bool:
    return (
        event.event == LEFT
        and event.participant.kind == ParticipantInfo.Kind.AGENT
        and event.participant.disconnect_reason in LOST
        and bool(event.room.name)
    )


# A log this process does not serve (it restarted since the call opened) is written and let go,
# as the reaper does: the told job's own entries then find no call here, and the reaper seals it.
async def _end(live: LiveParts, call: str, kept: calls.CallHead) -> bool:
    now = live.store.clock()
    started = now if kept.started_at is None else kept.started_at
    ended = CallEnded(reason="drained", ended_by="platform", ended_at=now, duration_s=max(now - started, 0.0))
    served = live.calls.find(call)
    if served is not None:
        return await served.log.append_first("call.ended", ended.dump()) is not None
    log = live.logs.writing(call, kept.agent)
    try:
        return await log.append_first("call.ended", ended.dump()) is not None
    finally:
        live.logs.forget(call)


# Only a phone has a number to call back: the caller's, or on an outbound call the one dialled.
async def _offer_a_call_back(session: AsyncSession, live: LiveParts, call: str, agent: str) -> None:
    facts = (await calls.facts_of_calls(session, [call])).get(call)
    if facts is None or facts.channel != Channel.phone:
        return
    number = facts.from_number if facts.direction == Direction.inbound else facts.to_number
    if not number:
        return
    wanted = CallbackRequested(channel=Channel.phone, number=number, via="overflow", call=call, contact=None)
    await live.logs.agent(agent).append(CALLBACK, wanted.dump())
