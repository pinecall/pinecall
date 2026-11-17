"""Tests for a simulated caller's ring by phone: its rule on the hand-over trunk, the leg dialled, the hang-up."""

from collections.abc import AsyncIterator

import pytest
from livekit import api
from livekit.protocol.room import RoomParticipantIdentity
from livekit.protocol.sip import CreateSIPInboundTrunkRequest, CreateSIPParticipantRequest, SIPInboundTrunkInfo

from runtime.enums import Env
from runtime.exceptions import ServiceUnavailable
from runtime.telephony.service.carrier import SipNames
from runtime.telephony.service.hand_over import HAND_OVER, USERNAME, password_of
from runtime.telephony.service.simulated_rings import (
    LEG,
    SIMULATION,
    admit_simulated_rings,
    callers_room,
    check_simulated_ring,
    hang_up_simulated_caller,
    ring_simulated_caller,
)
from runtime.wire.room import A_SIMULATED_CALLER
from tests.fakes.livekit import A_SECRET, Server, per_world

CALL = "call_0123456789abcdef0123456789abcdef"
NAMES = SipNames(
    domain="box.test",
    sip_domains={Env.production: "sip.box.test", Env.sandbox: "sip.sandbox.box.test"},
    livekit_secret=A_SECRET,
)


@pytest.fixture
async def servers() -> AsyncIterator[dict[Env, Server]]:
    """Each env's own LiveKit, closed after."""
    opened = per_world()
    yield opened
    for server in opened.values():
        await server.aclose()


async def with_the_trunk(servers: dict[Env, Server]) -> str:
    """The sandbox's LiveKit admitting production's hand-overs; the trunk's id."""
    trunk = SIPInboundTrunkInfo(name=HAND_OVER, allowed_addresses=["203.0.113.7"], auth_username=USERNAME)
    made = await servers[Env.sandbox].sip.create_inbound_trunk(CreateSIPInboundTrunkRequest(trunk=trunk))
    return made.sip_trunk_id


async def test_the_rule_seats_the_simulated_caller_alone_in_the_room_its_leg_dials(
    servers: dict[Env, Server],
) -> None:
    trunk_id = await with_the_trunk(servers)
    assert await admit_simulated_rings(servers)
    (rule,) = servers[Env.sandbox].dialled.rules.values()
    assert (rule.name, list(rule.trunk_ids), list(rule.inbound_numbers)) == (
        SIMULATION,
        [trunk_id],
        [A_SIMULATED_CALLER],
    )
    assert rule.rule.WhichOneof("rule") == "dispatch_rule_callee"
    assert (rule.rule.dispatch_rule_callee.room_prefix, rule.rule.dispatch_rule_callee.randomize) == ("", False)
    assert not rule.room_config.agents, "the gateway offers the room itself: the rule dispatches nobody"
    assert servers[Env.production].dialled.rules == {}


async def test_a_rule_that_stands_is_not_written_again(servers: dict[Env, Server]) -> None:
    await with_the_trunk(servers)
    await admit_simulated_rings(servers)
    asked = len(servers[Env.sandbox].dialled.requests)
    assert await admit_simulated_rings(servers)
    written = servers[Env.sandbox].dialled.requests[asked:]
    assert not [request for request in written if "List" not in type(request).__name__]


async def test_with_no_hand_over_trunk_no_ring_is_admitted(servers: dict[Env, Server]) -> None:
    assert not await admit_simulated_rings(servers)
    assert servers[Env.sandbox].dialled.rules == {}


async def test_where_the_envs_share_a_livekit_no_ring_is_admitted() -> None:
    server = Server()
    assert not await admit_simulated_rings({Env.production: server, Env.sandbox: server})
    await server.aclose()


async def test_the_leg_is_dialled_from_the_callers_own_room_to_the_calls_in_a_carriers_codec(
    servers: dict[Env, Server],
) -> None:
    await ring_simulated_caller(servers, NAMES, Env.sandbox, CALL)
    (leg,) = servers[Env.production].dialled.requests
    assert isinstance(leg, CreateSIPParticipantRequest)
    assert (leg.sip_call_to, leg.sip_number) == (CALL, A_SIMULATED_CALLER)
    assert (leg.room_name, leg.participant_identity) == (callers_room(CALL), LEG)
    assert (leg.trunk.hostname, leg.trunk.auth_username) == ("sip.sandbox.box.test", USERNAME)
    assert leg.trunk.auth_password == password_of(A_SECRET)
    assert leg.media.only_listed_codecs
    assert [(codec.name, codec.rate) for codec in leg.media.codecs] == [("PCMU", 8000)]
    assert leg.wait_until_answered
    assert servers[Env.sandbox].dialled.requests == []


async def test_a_ring_the_envs_sip_does_not_answer_is_said_in_a_sentence(servers: dict[Env, Server]) -> None:
    servers[Env.production].dialled.refusal = api.TwirpError("unavailable", "no answer", status=503)
    with pytest.raises(ServiceUnavailable, match="sandbox's SIP did not answer"):
        await ring_simulated_caller(servers, NAMES, Env.sandbox, CALL)


async def test_a_ring_is_refused_in_production_and_where_the_envs_share_a_livekit(
    servers: dict[Env, Server],
) -> None:
    check_simulated_ring(servers, NAMES, Env.sandbox)
    with pytest.raises(ServiceUnavailable, match="in the sandbox alone"):
        check_simulated_ring(servers, NAMES, Env.production)
    one = servers[Env.production]
    with pytest.raises(ServiceUnavailable, match="a SIP service each"):
        check_simulated_ring({Env.production: one, Env.sandbox: one}, NAMES, Env.sandbox)


async def test_hanging_up_takes_the_leg_out_of_the_callers_room(servers: dict[Env, Server]) -> None:
    await hang_up_simulated_caller(servers, CALL)
    (left,) = servers[Env.production].rooms.requests
    assert isinstance(left, RoomParticipantIdentity)
    assert (left.room, left.identity) == (callers_room(CALL), LEG)
