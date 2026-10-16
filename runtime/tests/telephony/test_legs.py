"""Tests for a call's phone legs: the caller's, what a leg says, and a SIP answer's word."""

import asyncio
from dataclasses import replace

import pytest
from livekit import api, rtc

from pinecall_runtime.channels.service.routes import Arrival, resolve_route
from pinecall_runtime.enums import Channel, Direction
from pinecall_runtime.exceptions import GatewayUnavailable
from pinecall_runtime.telephony.service.legs import (
    CALLER_NUMBER,
    DIALLED_NUMBER,
    TWILIO_ACCOUNT,
    arrival_of,
    caller_leg,
    end_reason_of,
)
from pinecall_runtime.wire.dispatch import Dispatch
from tests.channels.test_routes import A_PHONE, CALLER, IN_THE_SANDBOX, NUMBER
from tests.fakes.livekit import Room, seat
from tests.telephony.test_hand_over import HANDED

SIP = rtc.ParticipantKind.PARTICIPANT_KIND_SIP


def a_caller_seat() -> rtc.RemoteParticipant:
    """The caller's leg, seated, its number the one the call is from."""
    return seat("sip_caller", kind=SIP, attributes={CALLER_NUMBER: CALLER})


async def test_a_sip_leg_says_who_calls_and_which_number_they_dialled() -> None:
    leg = seat("sip_1", kind=SIP, attributes={CALLER_NUMBER: CALLER, DIALLED_NUMBER: NUMBER})
    arrived = await arrival_of(Dispatch(), Room("call_1", leg))
    assert arrived == A_PHONE


# Twilio stamps its leg with the account it came from; the gateway checks it against the number's.
async def test_a_leg_twilio_sent_says_the_account_it_came_from() -> None:
    attributes = {CALLER_NUMBER: CALLER, DIALLED_NUMBER: NUMBER, TWILIO_ACCOUNT: "AC_theirs"}
    arrived = await arrival_of(Dispatch(), Room("call_1", seat("sip_1", kind=SIP, attributes=attributes)))
    assert arrived == replace(A_PHONE, carrier_account="AC_theirs")


async def test_a_dispatch_naming_its_agent_does_not_wait_for_a_leg() -> None:
    arrived = await arrival_of(Dispatch(agent="front", caller="visitor"), Room("call_1"))
    assert arrived == Arrival(caller="visitor", channel=Channel.web, direction=Direction.inbound)


async def test_an_outbound_job_is_a_phone_call_it_places_itself() -> None:
    arrived = await arrival_of(Dispatch(direction=Direction.outbound, caller=CALLER), Room("call_1"))
    assert arrived == Arrival(caller=CALLER, channel=Channel.phone, direction=Direction.outbound)


async def test_a_ring_handed_over_waits_for_its_leg_to_say_the_number_it_dialled() -> None:
    leg = seat("sip_1", kind=SIP, attributes={CALLER_NUMBER: CALLER, DIALLED_NUMBER: NUMBER})
    arrived = await arrival_of(HANDED, Room("call_1", leg))
    assert arrived == A_PHONE
    assert resolve_route(HANDED, arrived, [], None) == IN_THE_SANDBOX


async def test_the_leg_already_seated_when_the_agent_arrives_is_found_without_waiting() -> None:
    offline = Room("call_1", a_caller_seat())
    found = await asyncio.wait_for(caller_leg(offline, Channel.phone), 0.5)
    assert found is not None
    assert found.identity == "sip_caller"


async def test_a_call_that_is_not_a_phones_is_answered_at_once_with_no_leg() -> None:
    assert await asyncio.wait_for(caller_leg(Room("call_1"), Channel.web), 0.5) is None


async def test_a_room_that_never_connected_has_no_leg_either() -> None:
    assert await asyncio.wait_for(caller_leg(Room("call_1"), Channel.phone), 6) is None


@pytest.mark.parametrize(
    ("code", "reason"),
    [
        ("486", "busy"),
        ("603", "busy"),
        ("480", "no_answer"),
        ("487", "no_answer"),
        ("500", "dial_failed"),
    ],
)
def test_the_carriers_answer_becomes_the_logs_own_word_for_it(code: str, reason: str) -> None:
    refused = api.TwirpError("unavailable", "sip", status=503, metadata={"sip_status_code": code})
    assert end_reason_of(refused) == reason


def test_anything_that_is_not_a_sip_answer_is_a_dial_that_failed() -> None:
    assert end_reason_of(GatewayUnavailable("GET /v1/agents/x/outbound-trunk: 409")) == "dial_failed"
    assert end_reason_of(api.TwirpError("internal", "no", status=500)) == "dial_failed"
