"""A call whose worker went away, offered again and handed to its taker; a caller alone offered one."""

import logging
from dataclasses import dataclass

from livekit.protocol.models import DisconnectReason, ParticipantInfo
from livekit.protocol.room import RoomParticipantIdentity
from livekit.protocol.webhook import WebhookEvent
from sqlalchemy.ext.asyncio import AsyncSession

from runtime.actor import Actor
from runtime.calls import service as calls
from runtime.calls.context import CallContext
from runtime.enums import Channel, Direction, Env, Medium
from runtime.exceptions import Conflict, Gone
from runtime.fleet import service as fleet
from runtime.live.parts import LiveParts
from runtime.live.served import Served
from runtime.live.service import openings
from runtime.livekit import A_PERSON, is_left_alone, participants_in
from runtime.telephony import service as telephony
from runtime.wire.base import BatchedEntry, Entry
from runtime.wire.dispatch import Dispatch
from runtime.wire.events import CallStarted, ErrorEvent

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


@dataclass(frozen=True, slots=True)
class TakenUp:
    """A call whose worker went away, as the worker that takes it up is answered."""

    agent: str
    context: CallContext
    medium: Medium
    started_at: float
    # Its turns and its tools' calls and answers, oldest first, behind those of the calls it continues.
    history: list[Entry]
    # How many entries the log took from the call's writers, the gateway's word of the loss among them.
    written: int
    # Which of the call's workers the asker now is.
    taken_up: int


# What the log says of a worker that went away, written as the call is taken up: the entry is the
# writer's own, so a batch the worker that left sends late finds the count moved and writes nothing.
WORKER_LOST = "worker_lost"
WORKER_LOST_SAYS = "the call's worker went away; another worker takes the call up where its log stands"


# livekit sends every room event of the box: all but an agent lost mid-call are answered and let be.
# Each env's LiveKit names its env in the URL its config sends to, so the room is asked of the LiveKit
# it lives on. In this order: a call whose worker is gone is offered, a caller alone is offered a worker, a
# room an agent joined or that ended is let go, and a room a hand-over bridges goes with either of
# its legs; each event moves one of the four.
async def hear_room_event(session: AsyncSession, live: LiveParts, env: Env, event: WebhookEvent) -> None:
    """One room event of an env's LiveKit: a call whose agent was lost and a caller alone are each offered a worker."""
    server = live.servers[env]
    await offer_stranded(session, live, env, event)
    await fleet.offer_arrival(live.offering, server, event)
    await fleet.forget_settled(live.offering, event)
    await telephony.unbridge(server, event)


# The caller is still in the room and the call is still open: it is offered to its env's fleet, and
# the worker that takes the job takes the call up where its log stands (`take_up_call`). The
# room is kept in the offers once, so a second delivery of the same event offers nothing, and it is
# let go when an agent joins. Nothing is written here: until 2026-11 the call was ended as `drained`
# on the spot and the job could only say one sentence and close the room. That end is now the job's
# own, said when no worker has a seat for the call (the overflow) or when it cannot be taken up, and
# the call back with it; a call nobody ever comes for is the reaper's, as before.
async def offer_stranded(session: AsyncSession, live: LiveParts, env: Env, event: WebhookEvent) -> str | None:
    """Offer the call whose agent the event says was lost to its fleet, to be taken up by another worker."""
    if not _tells_of_an_agent_lost(event):
        return None
    call = event.room.name
    kept = await calls.find_head(session, call)
    if kept is None or kept.sealed or kept.scope is None:
        return None
    if not await is_left_alone(live.servers[env], call):
        return None
    offered = await _offer(session, live, call, kept)
    reason = DisconnectReason.Name(event.participant.disconnect_reason)
    logger.warning("call %s: its worker went away (%s); offered to %s to be taken up", call, reason, offered)
    return call


# LiveKit takes about twenty seconds to say an agent is gone (it waits for the connection to come
# back), and the caller sits in silence for all of it: 23 to 26 s from a worker's pod deleted to the
# call handed on, measured on 2026-11-16. The gateway knows sooner. A worker reads its call's commands
# from a stream it opens again half a second after it ends, so a stream cut from the worker's end and
# still not open GONE_AFTER_S later is a worker that is gone, or one this gateway cannot reach, which
# cannot run a call either: no tool answers, no entry is written. The call is handed on then. The
# agent is taken out of the room first: a worker that was alive after all finds itself removed and
# leaves the call to the one that takes it up (`jobs.Job`), and the room holds one agent, never two.
# A call that ended as its worker left (its `call.ended` is on the log) and one whose caller is gone
# are left alone. LiveKit's own word, when it comes, finds the room offered or an agent in it.
GONE_AFTER_S = 3.0


async def hand_on_cut(live: LiveParts, served: Served) -> bool:
    """Hand on a spoken call whose worker stopped reading its commands; whether it was offered."""
    call = served.call
    async with live.sessions.begin() as session:
        kept = await calls.find_head(session, call)
        if kept is None or kept.sealed or kept.scope is None:
            return False
        if any(entry.type == "call.ended" for entry in await calls.read_whole(session, live.vault, call)):
            return False
        server = live.servers[kept.scope.env]
        seated = await participants_in(server, call)
        if not any(seat.kind in A_PERSON for seat in seated):
            return False
        for seat in seated:
            if seat.kind == ParticipantInfo.Kind.AGENT:
                await server.room.remove_participant(RoomParticipantIdentity(room=call, identity=seat.identity))
        offered = await _offer(session, live, call, kept)
    logger.warning(
        "call %s: its worker read no commands for %.0f s; offered to %s to be taken up", call, GONE_AFTER_S, offered
    )
    return True


async def _offer(session: AsyncSession, live: LiveParts, call: str, kept: calls.CallHead) -> str | None:
    scope = kept.scope
    if scope is None:
        return None
    dispatch = Dispatch(
        agent=kept.agent,
        org=scope.org,
        env=scope.env,
        holder=scope.holder or None,
        caller=await _number_to_call_back(session, call),
        worker_gone=True,
        entries_written=kept.written,
        started_at=kept.started_at,
    )
    return await live.offering.offer(call, await fleet.fleet_of_env(session, scope.env), dispatch)


# The worker went away, not the caller: the same call goes on in another worker. No quota, no token, no
# second call.ringing, and the socket that holds its agent stays bound, as the gateway never let go of
# the call. A call that never started, or that ended, has nothing to take up: its caller is told, as a
# call nobody can take is. The app a spoken golden's call was pinned to is not kept, and is not said again.
# It is asked before the worker joins the room: a room that holds an agent already, or no caller any
# more, is one somebody took up first or nobody waits in, and the asker leaves it as it is.
async def take_up_call(session: AsyncSession, live: LiveParts, actor: Actor, call: str) -> TakenUp:
    """Hand a call whose worker went away to the worker that takes it up, with what its log holds."""
    served = await openings.get_served(session, live, actor, call)
    if not await is_left_alone(live.servers[served.scope.env], call):
        raise Gone(f"call {call!r} has a worker already, or its caller left: there is nothing to take up")
    opening = await calls.opening_of(session, call)
    entries = await calls.read_whole(session, live.vault, call)
    started = next((entry for entry in entries if entry.type == "call.started"), None)
    if opening is None or started is None:
        raise Conflict(f"call {call!r} never started: there is nothing of it to take up")
    if any(entry.type == "call.ended" for entry in entries):
        raise Conflict(f"call {call!r} is over: nothing more can be written to it")
    said = CallStarted.model_validate(started.data)
    lost = ErrorEvent(code=WORKER_LOST, message=WORKER_LOST_SAYS, recoverable=True)
    taken = await calls.count_taken(session, call)
    told = BatchedEntry(type="error", data=lost.dump(), ts=live.store.clock())
    await served.log.append_many([told], after=taken)
    served.taken_up += 1
    return TakenUp(
        agent=served.agent,
        context=opening.context,
        medium=said.medium or Medium.voice,
        started_at=said.started_at,
        history=await calls.list_carried(session, live.vault, call),
        written=taken + 1,
        taken_up=served.taken_up,
    )


def _tells_of_an_agent_lost(event: WebhookEvent) -> bool:
    return (
        event.event == LEFT
        and event.participant.kind == ParticipantInfo.Kind.AGENT
        and event.participant.disconnect_reason in LOST
        and bool(event.room.name)
    )


# Only a phone has a number to call back: the caller's, or on an outbound call the one dialled.
async def _number_to_call_back(session: AsyncSession, call: str) -> str | None:
    facts = (await calls.facts_of_calls(session, [call])).get(call)
    if facts is None or facts.channel != Channel.phone:
        return None
    return (facts.from_number if facts.direction == Direction.inbound else facts.to_number) or None
