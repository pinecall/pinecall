"""A developer's own phone at a production number, carried to their sandbox copy: the gateway's half, the worker's."""

import asyncio
import hashlib
import hmac
import logging
import socket
from collections.abc import Mapping
from datetime import timedelta
from typing import Protocol

from livekit import api
from livekit.protocol.agent_dispatch import RoomAgentDispatch
from livekit.protocol.models import ParticipantInfo
from livekit.protocol.room import RoomConfiguration
from livekit.protocol.sip import (
    CreateSIPDispatchRuleRequest,
    CreateSIPInboundTrunkRequest,
    CreateSIPParticipantRequest,
    SIPDispatchRule,
    SIPDispatchRuleIndividual,
    SIPDispatchRuleInfo,
    SIPInboundTrunkInfo,
)
from livekit.protocol.webhook import WebhookEvent
from sqlalchemy.ext.asyncio import AsyncSession

from runtime.accounts import service as accounts
from runtime.actor import Scope
from runtime.enums import Env
from runtime.exceptions import ServiceUnavailable
from runtime.fleet import service as fleet
from runtime.livekit import Servers, close_room, participants_in
from runtime.telephony.service import sfu
from runtime.telephony.service.carrier import SipNames
from runtime.telephony.service.legs import sip_config
from runtime.wire.dispatch import AGENT_HEADER, HOLDER_HEADER, ORG_HEADER, Dispatch
from runtime.wire.worker import LegTrunk, RingHandoff

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
# How long the start waits for production's SIP name to say its address.
RESOLVED_WITHIN_S = 5.0

# Whose sandbox copy the ring is for rides the leg's INVITE, a header each; the sandbox's trunk
# turns each into an attribute of its leg.
HEADER_OF: Mapping[str, str] = {
    ORG_HEADER: "X-Pinecall-Org",
    AGENT_HEADER: "X-Pinecall-Agent",
    HOLDER_HEADER: "X-Pinecall-Holder",
}
# The sandbox's trunk's map of the leg's headers to its attributes.
ATTRIBUTE_OF: Mapping[str, str] = {header: attribute for attribute, header in HEADER_OF.items()}


# Which app sockets hold an agent now, and which of them a ring lands in, is `live`'s, above this
# domain. What keeps them is handed in under `agents_held`.
class AgentsHeld(Protocol):
    """The agents the orgs' apps hold now, as telephony asks about them."""

    def list_held(self, org: str, env: Env) -> frozenset[str]:
        """The agents a process holds in the org's env now, in any scope of it."""
        ...

    def list_taking_unclaimed(self, org: str, env: Env) -> frozenset[str]:
        """Of those, the ones that take a call nobody claimed."""
        ...

    async def is_known(self, org: str, slug: str) -> bool:
        """Whether the agent is the org's: held now, or its own log claimed by the org when it first was."""
        ...

    def find_ring_holder(self, scope: Scope, slug: str, caller: str | None) -> str | None:
        """The holder whose copy a ring at the agent lands in ("" the org's own); None when no app takes it."""
        ...


# ── the gateway's half: whose ring it is, and the sandbox's trunk and rule ──


# A developer's own phone dialling the production number reaches their sandbox copy, while they
# hold it, or the org's own copy when nobody of theirs does (an app the box hosts, a Studio agent);
# every other caller reaches production. Where the sandbox has a LiveKit of its own, the ring is
# dialled there over SIP, through the trunk the answer carries.
async def ring_for(
    session: AsyncSession,
    held: AgentsHeld,
    servers: Servers,
    names: SipNames,
    *,
    org: str,
    slug: str,
    caller: str,
) -> RingHandoff:
    """Where a production ring from this phone goes: a developer's scope and fleet, or nowhere."""
    # The agent is the org's the ring was for, never the fleet's key's own org.
    if not await held.is_known(org, slug):
        return RingHandoff()
    holder = held.find_ring_holder(Scope(org, Env.sandbox), slug, caller)
    member = await accounts.find_member_by_test_phone(session, caller)
    if holder is None or member is None or member.org != org:
        return RingHandoff()
    return RingHandoff(
        holder=holder,
        fleet=await fleet.fleet_of_env(session, Env.sandbox),
        trunk=hand_over_trunk(servers, names, caller),
    )


# Where each env has a LiveKit of its own, a developer's own phone at a production number is
# dialled from production's room to the sandbox's SIP, with a pair drawn from LiveKit's secret;
# where both share one, the sandbox's fleet is sent into the room instead.
def hand_over_trunk(servers: Servers, names: SipNames, caller: str) -> LegTrunk | None:
    """The trunk a ring is handed to the sandbox's SIP through; None where the envs share one."""
    if sfu.other_server(servers, Env.production) is None:
        return None
    return LegTrunk(
        hostname=names.get_sip_domain(Env.sandbox),
        transport="udp",
        username=USERNAME,
        password=_password(names),
        shown=caller,
    )


# The trunk lists no number: it admits whatever production dials, from production's media
# address alone (the one its SIP name names, and livekit-sip sends from) and with the pair. Its
# rule sends each ring to the sandbox's fleet as one diverted from production.
async def admit_hand_overs(session: AsyncSession, servers: Servers, names: SipNames) -> bool:
    """Leave the sandbox's own LiveKit admitting the rings production hands over; whether it does."""
    server = sfu.other_server(servers, Env.production)
    named = names.sip_domains.get(Env.production)
    if server is None or not named:
        return False
    addresses = await _resolve(named)
    if not addresses:
        logger.warning("production's SIP name %s names no address: the sandbox admits no hand-over", named)
        return False
    wanted = SIPInboundTrunkInfo(
        name=HAND_OVER,
        allowed_addresses=addresses,
        auth_username=USERNAME,
        auth_password=_password(names),
        headers_to_attributes=ATTRIBUTE_OF,
    )
    trunk_id = await _keep_trunk(server, wanted)
    await _keep_rule(server, trunk_id, await fleet.fleet_of_env(session, Env.sandbox))
    return True


# ── the worker's half: the leg, the bridge and its end ──


def password_of(secret: str) -> str:
    """The hand-over trunk's password: whoever holds LiveKit's secret could rewrite the trunk."""
    return hmac.new(secret.encode(), PAIR_OF, hashlib.sha256).hexdigest()


def headers_of(moved: Dispatch) -> dict[str, str]:
    """The headers the hand-over leg carries: the org, the agent and the developer it is for."""
    values = {ORG_HEADER: moved.org, AGENT_HEADER: moved.agent, HOLDER_HEADER: moved.holder}
    return {HEADER_OF[attribute]: value or "" for attribute, value in values.items()}


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
async def hand_on(server: api.LiveKitAPI, room_name: str, *, handed: RingHandoff, moved: Dispatch, number: str) -> bool:
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
async def unbridge(server: api.LiveKitAPI, event: WebhookEvent) -> bool:
    """Close a room a hand-over bridges once either of its legs left; whether it did."""
    if event.event != LEFT or event.participant.kind != ParticipantInfo.Kind.SIP:
        return False
    name = event.room.name
    if not event.participant.identity.startswith(LEG_PREFIX):
        present = await participants_in(server, name)
        if not any(participant.identity.startswith(LEG_PREFIX) for participant in present):
            return False
    await close_room(server, name)
    return True


# ── private ──


def _password(names: SipNames) -> str:
    if names.livekit_secret is None:
        raise ServiceUnavailable("LIVEKIT_API_KEY and LIVEKIT_API_SECRET are unset: this process cannot reach the SFU")
    return password_of(names.livekit_secret)


async def _resolve(name: str) -> list[str]:
    try:
        async with asyncio.timeout(RESOLVED_WITHIN_S):
            found = await asyncio.get_running_loop().getaddrinfo(
                name, None, family=socket.AF_INET, type=socket.SOCK_DGRAM
            )
    except (OSError, TimeoutError):
        return []
    return sorted({str(address[4][0]) for address in found})


async def _keep_trunk(server: api.LiveKitAPI, wanted: SIPInboundTrunkInfo) -> str:
    existing = await sfu.find_trunk(server, wanted.name)
    if existing is None:
        made = await server.sip.create_inbound_trunk(CreateSIPInboundTrunkRequest(trunk=wanted))
        return made.sip_trunk_id
    if (
        list(existing.allowed_addresses) == list(wanted.allowed_addresses)
        and existing.auth_username == wanted.auth_username
        and existing.auth_password == wanted.auth_password
        and dict(existing.headers_to_attributes) == dict(wanted.headers_to_attributes)
    ):
        return existing.sip_trunk_id
    await server.sip.update_inbound_trunk(existing.sip_trunk_id, wanted)
    return existing.sip_trunk_id


async def _keep_rule(server: api.LiveKitAPI, trunk_id: str, fleet_name: str) -> None:
    metadata = Dispatch(env=Env.sandbox, diverted_from=Env.production).dump()
    wanted = SIPDispatchRuleInfo(
        name=HAND_OVER,
        trunk_ids=[trunk_id],
        rule=SIPDispatchRule(dispatch_rule_individual=SIPDispatchRuleIndividual(room_prefix=sfu.ROOM_PREFIX)),
        room_config=RoomConfiguration(agents=[RoomAgentDispatch(agent_name=fleet_name, metadata=metadata)]),
    )
    existing = await sfu.find_rule(server, HAND_OVER)
    if existing is None:
        await server.sip.create_dispatch_rule(CreateSIPDispatchRuleRequest(dispatch_rule=wanted))
        return
    if list(existing.trunk_ids) == [trunk_id] and existing.room_config == wanted.room_config:
        return
    await server.sip.update_dispatch_rule(existing.sip_dispatch_rule_id, wanted)
