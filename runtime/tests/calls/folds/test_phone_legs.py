"""A call's time on the phone network: each phone leg from joining the room to leaving it, priced by its number."""

from runtime.calls.folds.phone_legs import phone_legs
from runtime.kit.text import JsonObject
from runtime.wire.base import Entry
from tests.calls.factories import entry


def a_leg(seq: int, identity: str, attributes: JsonObject) -> Entry:
    """A participant that joined the room at seq."""
    data: JsonObject = {"identity": identity, "kind": "caller", "attributes": attributes}
    return entry(seq, "participant.joined", data)


INBOUND: JsonObject = {
    "sip.callID": "SCL_1",
    "sip.ruleID": "SDR_1",
    "sip.twilio.callSid": "CA_1",
    "sip.trunkPhoneNumber": "+15550100133",
    "sip.phoneNumber": "+59899123456",
}


def test_a_phone_leg_runs_from_its_join_to_its_leave_and_is_priced_by_the_boxs_number() -> None:
    legs = phone_legs(
        [
            a_leg(1, "sip_caller", INBOUND),
            entry(71, "participant.left", {"identity": "sip_caller", "reason": "hung up"}),
        ]
    )
    assert [(leg.carrier, leg.direction, leg.number, leg.seconds) for leg in legs] == [
        ("twilio", "inbound", "+15550100133", 70.0)
    ]


def test_a_dialled_leg_still_up_at_the_end_is_priced_by_the_far_number_until_the_last_entry() -> None:
    dialled: JsonObject = {"sip.callID": "SCL_2", "sip.phoneNumber": "+14155550100"}
    legs = phone_legs([a_leg(1, "sip_out", dialled), entry(41, "call.ended", {})])
    assert [(leg.carrier, leg.direction, leg.number, leg.seconds) for leg in legs] == [
        ("sip", "outbound", "+14155550100", 40.0)
    ]


def test_a_participant_that_is_no_phone_leg_is_no_leg() -> None:
    assert phone_legs([a_leg(1, "visitor", {}), entry(9, "call.ended", {})]) == []
