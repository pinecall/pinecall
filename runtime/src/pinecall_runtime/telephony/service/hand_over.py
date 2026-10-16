"""A developer's own phone at a production number, carried to the sandbox's LiveKit by SIP."""

import hashlib
import hmac
import logging
from collections.abc import Mapping
from datetime import timedelta

from livekit import api
from livekit.protocol.models import ParticipantInfo
from livekit.protocol.sip import CreateSIPParticipantRequest
from livekit.protocol.webhook import WebhookEvent

from pinecall_runtime.calls import context
from pinecall_runtime.channels import service as channels
from pinecall_runtime.enums import Channel, Direction, Env
from pinecall_runtime.fleet import service as fleet
from pinecall_runtime.telephony.schemas import LegTrunk, RingHandoff
from pinecall_runtime.telephony.service.legs import sip_config
from pinecall_runtime.wire.dispatch import AGENT_HEADER, HOLDER_HEADER, ORG_HEADER, Dispatch

logger = logging.getLogger(__name__)

# The sandbox's trunk and its rule that admit production's hand-overs are both named so.
HAND_OVER = "hand-over"
USERNAME = "pinecall-hand-over"
# What the trunk's password is drawn under, from the LiveKit secret both envs' clusters share.
PAIR_OF = b"pinecall: a ring handed from production to the sandbox"
# The leg production's room dials, by its identity there.
LEG_PREFIX = "hand_over_"
LEFT = "participant_left"
# The sandbox's SIP answers a leg it admits at once: one it does not admit is given up on, and the
# caller reaches production's agent.
RINGS_S = 10.0

# Whose sandbox copy the ring is for rides the leg's INVITE, a header each; the sandbox's trunk
# turns each into an attribute of its leg.
HEADER_OF: Mapping[str, str] = {
    ORG_HEADER: "X-Pinecall-Org",
    AGENT_HEADER: "X-Pinecall-Agent",
    HOLDER_HEADER: "X-Pinecall-Holder",
}
# The sandbox's trunk's map of the leg's headers to its attributes.
ATTRIBUTE_OF: Mapping[str, str] = {header: attribute for attribute, header in HEADER_OF.items()}


def password_of(secret: str) -> str:
    """The hand-over trunk's password: whoever holds LiveKit's secret could rewrite the trunk."""
    return hmac.new(secret.encode(), PAIR_OF, hashlib.sha256).hexdigest()


def headers_of(moved: Dispatch) -> dict[str, str]:
    """The headers the hand-over leg carries: the org, the agent and the developer it is for."""
    values = {ORG_HEADER: moved.org, AGENT_HEADER: moved.agent, HOLDER_HEADER: moved.holder}
    return {HEADER_OF[attribute]: value or "" for attribute, value in values.items()}


# Only an undispatched ring at a production number can be a developer's own phone.
def may_be_a_developers(dispatch: Dispatch, arrival: channels.Arrival, route: context.Route) -> bool:
    """Whether to ask if this ring belongs in a developer's sandbox."""
    return (
        arrival.number is not None
        and dispatch.agent is None
        and arrival.direction is Direction.inbound
        and route.channel is Channel.phone
        and route.env is Env.production
    )


# The production number is dialled at the sandbox's SIP name and the caller is its From, so the
# sandbox's leg says both as a carrier's would; who the developer is rides in headers.
def leg_of(room_name: str, trunk: LegTrunk, moved: Dispatch, number: str) -> CreateSIPParticipantRequest:
    """The leg production's room dials to the sandbox's SIP, carrying whose ring it is."""
    request = CreateSIPParticipantRequest(
        sip_call_to=number,
        sip_number=trunk.shown,
        room_name=room_name,
        participant_identity=f"{LEG_PREFIX}{moved.holder}",
        headers=headers_of(moved),
        wait_until_answered=True,
    )
    request.ringing_timeout.FromTimedelta(timedelta(seconds=RINGS_S))
    request.trunk.CopyFrom(sip_config(trunk))
    return request


# Where the envs share a LiveKit the sandbox's fleet is sent into this room; where each has its
# own, this room dials the sandbox's SIP, and LiveKit bridges the caller and that leg here.
async def handed_on(
    server: api.LiveKitAPI, room_name: str, *, handed: RingHandoff, moved: Dispatch, number: str
) -> bool:
    """Send a developer's ring on to their sandbox copy; whether it went."""
    try:
        if handed.trunk is None:
            await fleet.dispatch_into(server, room_name, str(handed.fleet), moved)
        else:
            await server.sip.create_sip_participant(leg_of(room_name, handed.trunk, moved, number))
    except api.TwirpError:
        logger.warning("could not hand %s to %s: the call stays here", moved.agent, handed.fleet)
        return False
    return True


# LiveKit ends no SIP leg when another leaves: a caller who hung up would leave the developer's
# copy talking to nobody, and a copy that ended would leave the caller in silence.
async def unbridged(server: api.LiveKitAPI, event: WebhookEvent) -> bool:
    """Close a room a hand-over bridges once either of its legs left; whether it did."""
    if event.event != LEFT or event.participant.kind != ParticipantInfo.Kind.SIP:
        return False
    name = event.room.name
    if not event.participant.identity.startswith(LEG_PREFIX):
        seats = await fleet.seats_in(server, name)
        if not any(seat.identity.startswith(LEG_PREFIX) for seat in seats):
            return False
    await fleet.close_room(server, name)
    return True
