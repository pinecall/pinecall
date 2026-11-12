"""What a log says of its time on the phone network: each phone leg from joining the room to leaving it."""

from collections.abc import Iterable, Mapping
from dataclasses import replace

from runtime.providers.service import prices
from runtime.wire.base import Entry
from runtime.wire.room import ParticipantJoined, ParticipantLeft

# livekit-sip's attributes on a participant that is a phone leg.
SIP_CALL = "sip.callID"
# Only a phone leg that came in through a dispatch rule carries one.
SIP_RULE = "sip.ruleID"
TWILIO_CALL = "sip.twilio.callSid"
OWN_NUMBER = "sip.trunkPhoneNumber"
FAR_NUMBER = "sip.phoneNumber"


# A phone leg still up when the log ends is up until the call's last entry.
def phone_legs(entries: Iterable[Entry]) -> list[prices.PhoneLeg]:
    """Each leg of the call on the phone network, from when it joined the room until it left."""
    joined: dict[str, tuple[float, prices.PhoneLeg]] = {}
    found: list[prices.PhoneLeg] = []
    last = 0.0
    for entry in entries:
        last = entry.ts
        if entry.type == "participant.joined":
            arrived = ParticipantJoined.model_validate(entry.data)
            phone_leg = _phone_leg_of(arrived.attributes)
            if phone_leg is not None:
                joined[arrived.identity] = (entry.ts, phone_leg)
        elif entry.type == "participant.left":
            gone = ParticipantLeft.model_validate(entry.data)
            if gone.identity in joined:
                began, phone_leg = joined.pop(gone.identity)
                found.append(replace(phone_leg, seconds=entry.ts - began))
    found += [replace(phone_leg, seconds=last - began) for began, phone_leg in joined.values()]
    return found


def _phone_leg_of(attributes: Mapping[str, object]) -> prices.PhoneLeg | None:
    if SIP_CALL not in attributes:
        return None
    inbound = SIP_RULE in attributes
    number = attributes.get(OWN_NUMBER if inbound else FAR_NUMBER)
    return prices.PhoneLeg(
        carrier="twilio" if TWILIO_CALL in attributes else "sip",
        direction="inbound" if inbound else "outbound",
        number=number if isinstance(number, str) else "",
        seconds=0.0,
    )
