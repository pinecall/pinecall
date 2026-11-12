"""Tests for a ring handed to the sandbox by SIP: its pair, headers, dispatch and bridge."""

import secrets

from livekit import api
from livekit.protocol.models import ParticipantInfo, Room
from livekit.protocol.sip import CreateSIPParticipantRequest
from livekit.protocol.webhook import WebhookEvent
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from runtime.enums import Env
from runtime.jobs.service.client import GatewayClient
from runtime.telephony.service.hand_over import (
    ATTRIBUTE_OF,
    HEADER_OF,
    LEFT,
    LEG_PREFIX,
    USERNAME,
    hand_on,
    headers_of,
    password_of,
    unbridge,
)
from runtime.wire.dispatch import AGENT_HEADER, HOLDER_HEADER, ORG_HEADER, Dispatch
from runtime.wire.worker import LegTrunk, RingHandoff
from tests.conftest import Gateway, Tenant, holding, make_tenant, needs_the_services
from tests.fakes.livekit import A_SECRET, Server
from tests.jobs.service.test_arrival import (
    CALLER,
    NUMBER,
)

ROOM = "call-_+59899000001_abc"

MOVED = Dispatch(agent="recepcion", org="org_a", env=Env.sandbox, holder="m_ana")

LEG = f"{LEG_PREFIX}m_ana"

# A developer's sandbox copy, and what a ring from their own phone is sent on to it with.
HANDED = Dispatch(
    agent="front",
    org="org_a",
    env=Env.sandbox,
    holder="m_ana",
    caller=CALLER,
    diverted_from=Env.production,
)


TO_THE_SANDBOX = LegTrunk(
    hostname="sip.sandbox.box.test",
    transport="udp",
    username=USERNAME,
    password=password_of(A_SECRET),
    shown=CALLER,
)


def a_leaving(identity: str, kind: str) -> WebhookEvent:
    """LiveKit's word that a participant left production's room."""
    return WebhookEvent(
        event=LEFT,
        room=Room(name=ROOM),
        participant=ParticipantInfo(identity=identity, kind=kind),
    )


def a_bridge() -> Server:
    """Production's LiveKit with the caller and the hand-over leg in the room, and no agent."""
    server = Server()
    server.rooms.people = {ROOM}
    server.rooms.seated = {ROOM: [ParticipantInfo(identity=LEG, kind=ParticipantInfo.Kind.SIP)]}
    return server


def test_the_pair_is_drawn_from_livekits_secret_and_changes_with_it() -> None:
    assert password_of("a secret") == password_of("a secret")
    assert password_of("a secret") != password_of("another secret")
    assert "a secret" not in password_of("a secret")


def test_the_leg_carries_whose_ring_it_is_and_the_trunk_reads_each_header_back() -> None:
    headers = headers_of(MOVED)
    carried = {ATTRIBUTE_OF[header]: value for header, value in headers.items()}
    assert carried == {ORG_HEADER: "org_a", AGENT_HEADER: "recepcion", HOLDER_HEADER: "m_ana"}


async def test_the_sandbox_hanging_up_closes_the_room_and_with_it_the_callers_leg() -> None:
    server = a_bridge()
    assert await unbridge(server, a_leaving(LEG, "SIP"))
    assert server.rooms.people == set()
    await server.aclose()


async def test_the_caller_hanging_up_closes_the_room_and_with_it_the_leg_to_the_sandbox() -> None:
    server = a_bridge()
    server.rooms.people = set()
    assert await unbridge(server, a_leaving("sip_+59899000001", "SIP"))
    assert server.rooms.seated == {}
    await server.aclose()


async def test_a_room_no_hand_over_bridges_is_left_to_its_agent() -> None:
    server = Server()
    server.rooms.existing = {ROOM: True}
    assert not await unbridge(server, a_leaving("sip_+59899000001", "SIP"))
    assert not await unbridge(server, a_leaving("agent", "AGENT"))
    assert server.rooms.existing == {ROOM: True}
    await server.aclose()


async def test_where_the_sandbox_has_its_own_livekit_the_ring_is_dialled_to_its_sip() -> None:
    server = Server()
    handed = RingHandoff(holder="m_ana", fleet="pinecall-sandbox", trunk=TO_THE_SANDBOX)
    assert await hand_on(server, "call_1", handed=handed, moved=HANDED, number=NUMBER)
    (leg,) = server.dialled.requests
    assert isinstance(leg, CreateSIPParticipantRequest)
    assert (leg.sip_call_to, leg.sip_number, leg.room_name) == (NUMBER, CALLER, "call_1")
    assert (leg.trunk.hostname, leg.trunk.auth_username) == ("sip.sandbox.box.test", USERNAME)
    assert (dict(leg.headers)[HEADER_OF[ORG_HEADER]], dict(leg.headers)[HEADER_OF[HOLDER_HEADER]]) == (
        "org_a",
        "m_ana",
    )
    assert leg.wait_until_answered
    assert server.dispatcher.made == []
    await server.aclose()


async def test_where_the_worlds_share_a_livekit_the_sandboxs_fleet_is_sent_into_the_room() -> None:
    server = Server()
    handed = RingHandoff(holder="m_ana", fleet="pinecall-sandbox")
    assert await hand_on(server, "call_1", handed=handed, moved=HANDED, number=NUMBER)
    (sent,) = server.dispatcher.made
    assert (sent.room, sent.agent_name, Dispatch.parse(sent.metadata)) == (
        "call_1",
        "pinecall-sandbox",
        HANDED,
    )
    assert server.dialled.requests == []
    await server.aclose()


async def test_a_hand_over_the_sandbox_does_not_answer_leaves_the_ring_here() -> None:
    server = Server()
    server.dialled.refusal = api.TwirpError("unavailable", "no answer", status=503)
    handed = RingHandoff(holder="m_ana", fleet="pinecall-sandbox", trunk=TO_THE_SANDBOX)
    assert not await hand_on(server, "call_1", handed=handed, moved=HANDED, number=NUMBER)
    await server.aclose()


# A Studio agent is held by the gateway in the org's own corner: a developer's phone at the
# production number reached nothing of the sandbox's (2026-11-05), the hand-over wanted a person's.
@needs_the_services
async def test_a_production_ring_from_a_members_phone_is_handed_to_the_orgs_own_sandbox_copy_and_to_no_other_orgs(
    gateway: Gateway, tenant: Tenant, agent: str, fleet: GatewayClient, sessions: async_sessionmaker[AsyncSession]
) -> None:
    caller = a_number()
    async with holding(gateway, tenant, agent):
        assert (await fleet.ring_for(agent, tenant.org, caller)).holder is None, "a phone nobody said was theirs"
        await gateway.http.put("/v1/line/from", json={"number": caller}, headers=tenant.person)
        assert (await fleet.ring_for(agent, tenant.org, caller)).holder == ""
        # Another org's member saying the phone is theirs takes it: it diverts nothing of this org's.
        other = await make_tenant(sessions)
        await gateway.http.put("/v1/line/from", json={"number": caller}, headers=other.person)
        assert (await fleet.ring_for(agent, tenant.org, caller)).holder is None
        await gateway.http.delete("/v1/line/from", headers=other.person)


def a_number() -> str:
    """A number of this test alone: a number is one org's on the whole box."""
    return f"+1555{secrets.randbelow(10**7):07d}"
