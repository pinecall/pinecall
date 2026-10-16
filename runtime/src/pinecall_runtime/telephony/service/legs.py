"""A call's phone legs in its room: the caller's, one dialled in, the caller sent on, the tones."""

import asyncio
import contextlib
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import timedelta

from livekit import api, rtc
from livekit.agents import utils
from livekit.protocol.sip import (
    CreateSIPParticipantRequest,
    SIPOutboundConfig,
    SIPTransferReason,
    SIPTransferStatus,
    SIPTransport,
    TransferSIPParticipantRequest,
    TransferSIPParticipantResponse,
)

from pinecall_runtime.channels import service as channels
from pinecall_runtime.enums import Channel, Direction
from pinecall_runtime.telephony.schemas import LegTrunk, Transport
from pinecall_runtime.wire.dispatch import Dialling, Dispatch
from pinecall_runtime.wire.events import CallTransferred
from pinecall_runtime.wire.parts import EndReason, TransferMode

logger = logging.getLogger(__name__)

# The caller's leg can join a moment after the agent, and livekit's own wait never times out.
WAIT_FOR_THE_LEG_S = 5.0
# livekit's attribute names for a SIP leg all start so.
SIP_PREFIX = "sip."
# The number the caller dials from, and the one they dialled.
CALLER_NUMBER = "sip.phoneNumber"
DIALLED_NUMBER = "sip.trunkPhoneNumber"
# The Twilio account a leg Twilio sent came from: livekit-sip reads X-Twilio-AccountSid into it.
TWILIO_ACCOUNT = "sip.twilio.accountSid"
# livekit's convention for a dialled leg's identity, which every dialled leg follows.
LEG_PREFIX = "sip_"
NO_LEG = "{verb}: this call has no phone leg"
# A dialled leg rings for less than livekit's 30 s; a tone plays meanwhile, so silence is not
# taken for a dropped call.
RINGING_S = 25.0
# RFC 4733 codes, as publish_dtmf takes them. A comma pauses, as in a dialler's string; any
# other character refuses the whole sequence, since half a card number is worse than none. Some
# carriers merge tones sent back to back into one long press.
CODES: dict[str, int] = {**{str(digit): digit for digit in range(10)}, "*": 10, "#": 11}
PAUSE = ","
PAUSE_S = 0.5
BETWEEN_TONES_S = 0.12
# SIP answers: busy and declined; the three ways of nobody picking up.
BUSY = frozenset({"486", "603"})
NO_ANSWER = frozenset({"408", "480", "487"})
TRANSPORTS: dict[Transport, SIPTransport] = {
    "auto": SIPTransport.SIP_TRANSPORT_AUTO,
    "udp": SIPTransport.SIP_TRANSPORT_UDP,
    "tcp": SIPTransport.SIP_TRANSPORT_TCP,
    "tls": SIPTransport.SIP_TRANSPORT_TLS,
}

# The SFU keeps no outbound trunk: each leg carries its own, so a restarted SFU dials on.
# Asked each time a verb dials: the gateway checks the org's dial guards and its limits first,
# so a refusal carries their reason into the log. Never cached.
type Trunks = Callable[[str], Awaitable["Trunk"]]
# Asked before a cold transfer: the same guards, and no trunk, since a REFER dials nothing of ours.
type SentOn = Callable[[str], Awaitable[None]]


@dataclass(frozen=True, slots=True)
class Trunk:
    """How a number is dialled: the trunk inline, and the org's number shown."""

    config: SIPOutboundConfig
    shown: str | None = None


@dataclass(frozen=True, slots=True)
class Legs:
    """How a second leg of the call is judged: the guards and the trunk, or the guards alone."""

    trunk: Trunks
    sent_on: SentOn


# livekit's wait never times out; a room that never connected raises, and has no leg either.
# The first SIP seat is the caller; later ones came from room.invite or a warm transfer.
async def caller_leg(room: rtc.Room, channel: Channel) -> rtc.RemoteParticipant | None:
    """The caller's SIP seat, waited for a moment on a phone call; none on any other."""
    if channel is Channel.phone and _phone_in(room) is None:
        with contextlib.suppress(TimeoutError, RuntimeError):
            async with asyncio.timeout(WAIT_FOR_THE_LEG_S):
                await utils.wait_for_participant(room, kind=rtc.ParticipantKind.PARTICIPANT_KIND_SIP)
    return _phone_in(room)


async def arrival_of(dispatch: Dispatch, room: rtc.Room) -> channels.Arrival:
    """What the job's dispatch and the room's SIP leg say of the call."""
    outbound = dispatch.direction is Direction.outbound
    # A dispatch that names its agent does not wait for a SIP leg, but a ring handed over from
    # production does: its leg says the number dialled. An outbound job places its own.
    is_placed = outbound or (dispatch.agent is not None and dispatch.diverted_from is None)
    leg = None if is_placed else await caller_leg(room, Channel.phone)
    data = {} if leg is None else dict(leg.attributes)
    dialled = data.get(DIALLED_NUMBER)
    return channels.Arrival(
        caller=data.get(CALLER_NUMBER) or dispatch.caller or room.name,
        channel=Channel.phone if outbound or dialled else Channel.web,
        direction=Direction.outbound if outbound else Direction.inbound,
        number=dialled,
        carrier_account=data.get(TWILIO_ACCOUNT),
    )


def is_a_phone(attributes: dict[str, str]) -> bool:
    """Whether a seat's attributes are a SIP leg's."""
    return any(key.startswith(SIP_PREFIX) for key in attributes)


def sip_config(leg: LegTrunk) -> SIPOutboundConfig:
    """The inline trunk livekit dials a leg through."""
    return SIPOutboundConfig(
        hostname=leg.hostname,
        transport=TRANSPORTS[leg.transport],
        auth_username=leg.username,
        auth_password=leg.password,
    )


# The caller is sent on only past the org's guards for a second leg (shape, pace, the ledger's
# row), as a warm transfer is: the REFER is a leg the carrier dials on the org's bill.
async def sent_on(server: api.LiveKitAPI, room: rtc.Room, channel: Channel, legs: Legs, to: str) -> CallTransferred:
    """Send the caller on to another number by a REFER of their own leg."""
    leg = await caller_leg(room, channel)
    if leg is None:
        return _stayed(to, "cold", NO_LEG.format(verb="call.transfer"))
    try:
        await legs.sent_on(to)
    except Exception as refused:
        logger.warning("call.transfer: the guards refused the leg", exc_info=True)
        return _stayed(
            to, "cold", str(refused) or f"call.transfer: no outbound SIP trunk is configured, so {to} cannot be dialled"
        )
    request = TransferSIPParticipantRequest(
        participant_identity=leg.identity, room_name=room.name, transfer_to=to, play_dialtone=True
    )
    try:
        answer = await server.sip.transfer_sip_participant(request)
    except api.TwirpError as refused:
        return _stayed(to, "cold", f"call.transfer: {refused}")
    # A transfer can fail without raising.
    if answer.status != SIPTransferStatus.STS_TRANSFER_SUCCESSFUL:
        return _stayed(to, "cold", _did_not_take(answer))
    return CallTransferred(to=to, mode="cold", ok=True)


# Waiting until answered is what makes busy and no answer seen; without it the request returns as
# soon as the INVITE went out.
async def dialled_in(server: api.LiveKitAPI, room_name: str, legs: Legs, to: str) -> CallTransferred:
    """Dial a person into the call's room, and wait for them to answer."""
    request = await leg_to(room_name, legs, to, verb="call.transfer")
    if isinstance(request, str):
        return _stayed(to, "warm", request)
    request.wait_until_answered = True
    request.play_dialtone = True
    request.ringing_timeout.FromTimedelta(timedelta(seconds=RINGING_S))
    try:
        await server.sip.create_sip_participant(request)
    except api.TwirpError as refused:
        return _stayed(to, "warm", f"call.transfer: {refused}")
    return CallTransferred(to=to, mode="warm", ok=True)


async def leg_to(room_name: str, legs: Legs, to: str, *, verb: str) -> CreateSIPParticipantRequest | str:
    """The request that dials a leg into the room, or why it cannot be dialled."""
    try:
        trunk = await legs.trunk(to)
    except Exception as refused:
        logger.warning("%s: no trunk to dial through", verb, exc_info=True)
        return str(refused) or f"{verb}: no outbound SIP trunk is configured, so {to} cannot be dialled"
    request = CreateSIPParticipantRequest(
        trunk=trunk.config, sip_call_to=to, room_name=room_name, participant_identity=f"{LEG_PREFIX}{to}"
    )
    if trunk.shown is not None:
        request.sip_number = trunk.shown
    return request


# The media plane holds the ceiling, so a worker that dies does not leave the far end on the line.
def outbound_leg(room_name: str, dial: Dialling, trunk: LegTrunk) -> CreateSIPParticipantRequest:
    """The request that places an outbound call's leg, waiting for the far end to answer."""
    request = CreateSIPParticipantRequest(
        sip_call_to=dial.to,
        sip_number=dial.shown,
        room_name=room_name,
        participant_identity=f"{LEG_PREFIX}{dial.to}",
        wait_until_answered=True,
    )
    request.ringing_timeout.FromTimedelta(timedelta(seconds=RINGING_S))
    if dial.max_duration_s:
        request.max_call_duration.FromTimedelta(timedelta(seconds=dial.max_duration_s))
    request.trunk.CopyFrom(sip_config(trunk))
    return request


def wrong_tone(digits: str) -> str | None:
    """Why the sequence cannot be keyed, or None when every character is a tone or a pause."""
    wrong = next((digit for digit in digits if digit != PAUSE and digit not in CODES), None)
    return None if wrong is None else f"call.dtmf: {wrong!r} is not a touch tone (0-9, * or #), and nothing was sent"


async def send_tones(room: rtc.Room, digits: str) -> None:
    """Key each tone down the line in order, a comma a pause; a refusal raises."""
    for digit in digits:
        if digit == PAUSE:
            await asyncio.sleep(PAUSE_S)
            continue
        await room.local_participant.publish_dtmf(code=CODES[digit], digit=digit)
        await asyncio.sleep(BETWEEN_TONES_S)


# The SIP answer livekit passes on: busy and declined, no answer, anything else a dial that failed.
def end_reason_of(refused: Exception) -> EndReason:
    """The log's own word for a leg that never came up."""
    answer = refused.metadata.get("sip_status_code") if isinstance(refused, api.TwirpError) else None
    if answer in BUSY:
        return "busy"
    if answer in NO_ANSWER:
        return "no_answer"
    return "dial_failed"


def _phone_in(room: rtc.Room) -> rtc.RemoteParticipant | None:
    return next(
        (seat for seat in room.remote_participants.values() if seat.kind == rtc.ParticipantKind.PARTICIPANT_KIND_SIP),
        None,
    )


def _stayed(to: str, mode: TransferMode, why: str) -> CallTransferred:
    return CallTransferred(to=to, mode=mode, ok=False, error=why)


def _did_not_take(answer: TransferSIPParticipantResponse) -> str:
    reason = SIPTransferReason.Name(answer.reason).removeprefix("STR_").lower()
    return f"call.transfer: {reason}, SIP {answer.sip_status.code} {answer.sip_status.status}".strip()
