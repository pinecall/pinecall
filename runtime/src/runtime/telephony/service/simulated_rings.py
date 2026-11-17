"""A simulated caller's ring by phone: the rule that seats its leg in the call's room, the leg dialled, the hang-up."""

from datetime import timedelta

from livekit import api
from livekit.protocol.room import RoomParticipantIdentity
from livekit.protocol.sip import (
    CreateSIPDispatchRuleRequest,
    CreateSIPParticipantRequest,
    SIPCodec,
    SIPDispatchRule,
    SIPDispatchRuleCallee,
    SIPDispatchRuleInfo,
    SIPMediaConfig,
)

from runtime.enums import Env
from runtime.exceptions import ServiceUnavailable
from runtime.fleet import service as fleet
from runtime.livekit import ROOM_GONE, Servers
from runtime.telephony.service import hand_over, sfu
from runtime.telephony.service.carrier import SipNames
from runtime.telephony.service.legs import sip_config
from runtime.wire.room import A_SIMULATED_CALLER
from runtime.wire.worker import LegTrunk

# The rule on the hand-over trunk that seats a simulated caller's leg, by name.
SIMULATION = "simulation"
# The env whose LiveKit holds the caller's own room, and whose SIP dials the leg: the hand-over's path.
RINGS_FROM = Env.production
# The leg the caller's room dials, by its identity there.
LEG = "simulated_ring"
# The room a simulated caller speaks in, beside the call's own.
OF_THE_CALLER = "-caller"
# The env's SIP answers an inbound leg only once somebody in its room hears it (livekit-sip waits for
# the leg's track to be subscribed): a simulated caller's leg rings until the job the room is offered
# to arrives, so it rings for as long as an agent may take to join.
RINGS_S = fleet.AN_AGENT_JOINS_WITHIN_S
# What a carrier sends a call in: G.711 µ-law at 8 kHz. Two livekit-sip would agree on G.722, which
# no phone network carries to us, and the agent would hear a line twice as wide as a caller's.
A_CARRIERS_CODEC = SIPCodec(name="PCMU", rate=8000)

NO_PATH = (
    "a simulated caller rings by phone in the sandbox alone, on a box whose envs have a SIP service each: "
    "the {env}'s SIP admits no leg of this box's own"
)


def callers_room(call: str) -> str:
    """The room a simulated caller of this call speaks in, on the LiveKit its leg is dialled from."""
    return f"{call}{OF_THE_CALLER}"


# The sandbox's trunk that admits production's hand-overs admits this leg too: it comes from the same
# address with the same pair, and a second trunk with no number would be a second default one, which
# livekit refuses to choose between. What tells the two apart is who calls: this rule lists the
# simulated caller alone, and livekit prefers a rule that names the calling number (its
# `DispatchRulePriority`). The rule is of the callee's kind with no prefix, so the room is the number
# dialled, and the leg dials the call's own id: the caller lands in the room the gateway named, as
# its web twin does, and the gateway offers that room as it offers any.
async def admit_simulated_rings(servers: Servers) -> bool:
    """Leave the sandbox's LiveKit seating a simulated caller's leg in the room it dials; whether it does."""
    server = sfu.other_server(servers, RINGS_FROM)
    trunk = None if server is None else await sfu.find_trunk(server, hand_over.HAND_OVER)
    if server is None or trunk is None:
        return False
    wanted = SIPDispatchRuleInfo(
        name=SIMULATION,
        trunk_ids=[trunk.sip_trunk_id],
        inbound_numbers=[A_SIMULATED_CALLER],
        rule=SIPDispatchRule(dispatch_rule_callee=SIPDispatchRuleCallee()),
    )
    existing = await sfu.find_rule(server, SIMULATION)
    if existing is None:
        await server.sip.create_dispatch_rule(CreateSIPDispatchRuleRequest(dispatch_rule=wanted))
    elif list(existing.trunk_ids) != list(wanted.trunk_ids) or list(existing.inbound_numbers) != [A_SIMULATED_CALLER]:
        await server.sip.update_dispatch_rule(existing.sip_dispatch_rule_id, wanted)
    return True


def check_simulated_ring(servers: Servers, names: SipNames, env: Env) -> None:
    """Refuse a ring the env's SIP would not admit: another env than the sandbox, or one LiveKit for both."""
    if env is RINGS_FROM or hand_over.hand_over_trunk(servers, names, A_SIMULATED_CALLER) is None:
        raise ServiceUnavailable(NO_PATH.format(env=env.value))


def ring_of(call: str, trunk: LegTrunk) -> CreateSIPParticipantRequest:
    """The leg a simulated caller's room dials to the call's room, in a carrier's codec."""
    request = CreateSIPParticipantRequest(
        sip_call_to=call,
        sip_number=trunk.shown,
        room_name=callers_room(call),
        participant_identity=LEG,
        wait_until_answered=True,
        media=SIPMediaConfig(only_listed_codecs=True, codecs=[A_CARRIERS_CODEC]),
    )
    request.ringing_timeout.FromTimedelta(timedelta(seconds=RINGS_S))
    request.trunk.CopyFrom(sip_config(trunk))
    return request


# Answered means heard: this returns once an agent sits in the call's room, so the room is offered
# while the leg rings, never after it (awaited first, on 2026-11-17, the leg rang ten seconds in a
# room nobody had been sent to and was given up).
async def ring_simulated_caller(servers: Servers, names: SipNames, env: Env, call: str) -> None:
    """Dial the simulated caller's leg into the call's room and wait for the env's SIP to answer it."""
    trunk = hand_over.hand_over_trunk(servers, names, A_SIMULATED_CALLER)
    if trunk is None:
        raise ServiceUnavailable(NO_PATH.format(env=env.value))
    try:
        await servers[RINGS_FROM].sip.create_sip_participant(ring_of(call, trunk))
    except api.TwirpError as refused:
        raise ServiceUnavailable(
            f"the {env.value}'s SIP did not answer the simulated caller's ring: {refused.message}"
        ) from refused


# The leg is the caller's phone: taking it out of the caller's room is a BYE to the env's SIP, which
# the agent hears as any caller hanging up.
async def hang_up_simulated_caller(servers: Servers, call: str) -> None:
    """Hang up the simulated caller's leg; one already gone is fine."""
    leaving = RoomParticipantIdentity(room=callers_room(call), identity=LEG)
    try:
        await servers[RINGS_FROM].room.remove_participant(leaving)
    except api.TwirpError as refused:
        if refused.code != ROOM_GONE:
            raise
