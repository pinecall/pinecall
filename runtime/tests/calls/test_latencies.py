"""The latencies a call's turns carry: the medians, the samples, the phone legs, the barge-ins."""

from pinecall_runtime.calls.latencies import MEASURES, interruption_delays, medians, phone_legs, samples
from pinecall_runtime.calls.reducer import reduce
from pinecall_runtime.kit.text import JsonObject
from pinecall_runtime.wire.base import Entry
from pinecall_runtime.wire.state import AgentTurn, UserTurn
from tests.calls.factories import GOLDEN, entry

GOLDEN_TURNS = reduce(GOLDEN).turns


def test_the_medians_are_the_six_measures_over_the_turns_that_carried_them() -> None:
    rows = {median.name: (median.seconds, median.turns) for median in medians([GOLDEN_TURNS])}
    assert list(rows) == list(MEASURES)
    assert rows["e2e_latency"] == (0.94, 5)
    assert (round(rows["talk_share"][0], 2), rows["talk_share"][1]) == (0.75, 1)


def test_the_talk_share_is_the_agents_part_of_the_time_anybody_spoke() -> None:
    def turn(role: str, started: float, stopped: float) -> UserTurn | AgentTurn:
        timing = {"started_speaking_at": started, "stopped_speaking_at": stopped}
        if role == "user":
            return UserTurn.model_validate({"speech_id": "u", "text": "a", "metrics": timing})
        return AgentTurn.model_validate({"speech_id": "a", "text": "b", "interrupted": False, "metrics": timing})

    first = [turn("user", 0.0, 2.0), turn("agent", 3.0, 4.0), turn("user", 5.0, 6.0)]
    second = [turn("agent", 100.0, 101.0), turn("user", 102.0, 104.0), turn("agent", 103.5, 105.0)]
    assert samples(first)["talk_share"] == [1.0 / 4.0]
    assert samples(second)["talk_share"] == [2.5 / 4.5]


def test_a_measure_no_turn_carried_gets_no_row_at_all() -> None:
    callers = [turn for turn in GOLDEN_TURNS if isinstance(turn, UserTurn)]
    rows = {median.name: median.seconds for median in medians([callers])}
    # Only the caller spoke: the agent's share of the talking is nothing.
    assert list(rows) == ["transcription_delay", "end_of_turn_delay", "talk_share"]
    assert rows["talk_share"] == 0.0


def test_a_sample_keeps_every_value_in_turn_order_and_drops_the_measures_nobody_took() -> None:
    replies = [turn for turn in GOLDEN_TURNS if isinstance(turn, AgentTurn)]
    taken = samples(GOLDEN_TURNS)
    timed = [turn.metrics.e2e_latency for turn in replies]
    assert taken["e2e_latency"] == [seconds for seconds in timed if seconds is not None]
    assert None in timed
    assert samples([]) == {}


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


def test_a_barge_in_is_timed_from_the_caller_cutting_in_to_the_agent_falling_quiet() -> None:
    assert [round(seconds, 2) for seconds in interruption_delays(GOLDEN)] == [0.33]


def test_a_reply_that_ended_on_its_own_while_the_caller_spoke_is_no_barge_in() -> None:
    lines: list[tuple[str, JsonObject, float]] = [
        ("agent.state", {"state": "speaking"}, 1.0),
        ("user.state", {"state": "speaking"}, 2.0),
        ("turn.agent", {"interrupted": False}, 2.5),
        ("agent.state", {"state": "listening"}, 2.5),
        ("agent.state", {"state": "speaking"}, 4.0),
        ("user.state", {"state": "speaking"}, 5.0),
        ("agent.state", {"state": "listening"}, 5.2),
        ("turn.agent", {"interrupted": True}, 5.2),
    ]
    written = [entry(seq, kind, data).model_copy(update={"ts": ts}) for seq, (kind, data, ts) in enumerate(lines, 1)]
    assert [round(seconds, 2) for seconds in interruption_delays(written)] == [0.2]
