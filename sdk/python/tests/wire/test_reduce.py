"""The reducer: the golden log folds to the runtime's state from any cut, and past a bad entry."""

import json

import pytest

from pinecall.wire._names import JsonObject
from pinecall.wire.events import EVENTS
from pinecall.wire.frames import Entry
from pinecall.wire.reduce import UNREADABLE, apply, initial_state, reduce
from pinecall.wire.state import Gap, State
from tests.wire.entries import AGENT, BOSS, CALL, CALLER, LINE, ROOM, SEAT, TOOL, a_summary, entry
from tests.wire.golden import GOLDEN_STATE, golden_entries

GOLDEN = golden_entries()
EXPECTED = json.loads(GOLDEN_STATE.read_text(encoding="utf-8"))

# ── the golden log ──


def test_the_golden_log_reduces_to_the_golden_state_whole() -> None:
    assert reduce(GOLDEN).written() == EXPECTED


def test_the_golden_carries_both_kinds_of_entry() -> None:
    assert {item.ephemeral for item in GOLDEN} == {True, False}


@pytest.mark.parametrize("cut", range(len(GOLDEN) + 1))
def test_a_state_kept_at_any_cut_folds_the_rest_to_the_same_state(cut: int) -> None:
    state = reduce(GOLDEN[:cut])
    for item in GOLDEN[cut:]:
        state = apply(state, item)
    assert state.written() == EXPECTED


@pytest.mark.parametrize("cut", range(len(GOLDEN)))
def test_a_gap_carrying_a_snapshot_of_any_cut_resumes_to_the_same_state(cut: int) -> None:
    at = GOLDEN[cut]
    snapshot = reduce(GOLDEN[:cut]).written()
    gap = at.model_copy(
        update={"type": "log.gap", "data": {"from_seq": 1, "to_seq": cut, "snapshot": snapshot}}
    )
    resumed = reduce([gap, *GOLDEN[cut:]])
    ours = Gap(from_seq=1, to_seq=cut)
    assert resumed.gaps.count(ours) == 1
    assert [gap for gap in resumed.gaps if gap != ours] == State.model_validate(EXPECTED).gaps
    assert resumed.model_copy(update={"gaps": []}).written() == {**EXPECTED, "gaps": []}


# ── the call ──


def test_an_empty_log_is_idle_with_nothing_known() -> None:
    state = reduce([])
    assert (state.seq, state.status, state.call) == (0, "idle", None)
    assert state.turns == []
    assert state.tools == []
    assert state.app_state == {}


def test_a_ringing_call_knows_who_is_calling_before_media_is_up() -> None:
    route: JsonObject = {"channel": "phone", "number": "+34955111222"}
    state = reduce([entry(1, "call.ringing", {**LINE, "route": route, "caller": CALLER})])
    assert (state.status, state.direction, state.seq, state.call) == ("ringing", "inbound", 1, CALL)
    assert state.caller is not None
    assert state.caller.name == "Marta"
    assert state.started_at is None


def test_the_summary_brings_the_bill_and_the_outcome() -> None:
    tts: JsonObject = {
        "type": "tts_usage",
        "provider": "cartesia",
        "model": "sonic",
        "characters_count": 90,
    }
    state = reduce([entry(1, "call.summary", a_summary([tts]))])
    assert (state.outcome, state.end_reason) == ("moved the appointment", "caller_hung_up")
    assert state.cost is not None
    assert state.cost.usd == 0.02
    assert state.usage[0].type == "tts_usage"


def test_the_reason_the_call_ended_with_is_not_overwritten_by_the_summary() -> None:
    ended: JsonObject = {
        "reason": "agent_hung_up",
        "ended_by": "agent",
        "ended_at": 2.0,
        "duration_s": 1.0,
    }
    state = reduce([entry(1, "call.ended", ended), entry(2, "call.summary", a_summary([]))])
    assert state.end_reason == "agent_hung_up"


# ── the talk ──


def test_a_finished_turn_clears_the_words_on_screen() -> None:
    state = reduce(
        [
            entry(1, "user.transcript", {"text": "quiero cam", "final": False}, ephemeral=True),
            entry(
                2,
                "turn.user",
                {"speech_id": "u1", "text": "Quiero cambiar la cita.", "metrics": {}},
            ),
        ]
    )
    assert state.live.user is None
    assert [turn.text for turn in state.turns] == ["Quiero cambiar la cita."]


def test_the_agents_words_on_screen_are_its_deltas_joined() -> None:
    def word(seq: int, text: str, start: float) -> Entry:
        data: JsonObject = {"speech_id": "a1", "text": text, "final": False, "start": start}
        return entry(seq, "agent.transcript", data, ephemeral=True)

    def token(seq: int, text: str) -> Entry:
        data: JsonObject = {"speech_id": "a2", "text": text, "final": False}
        return entry(seq, "agent.transcript", data, ephemeral=True)

    assert reduce(
        [word(1, "Claro,", 0), word(2, "el", 0.4), word(3, "viernes", 0.6)]
    ).live.agent == ("Claro, el viernes")
    assert reduce(
        [token(1, "Hola"), token(2, " de"), token(3, " nue"), token(4, "vo")]
    ).live.agent == ("Hola de nuevo")
    turn: JsonObject = {"speech_id": "a1", "text": "Claro.", "interrupted": False, "metrics": {}}
    assert reduce([word(1, "Claro", 0), entry(2, "turn.agent", turn)]).live.agent is None


# ── the tools ──


def test_a_tool_result_closes_its_call_as_done_or_failed() -> None:
    done = reduce(
        [
            entry(1, "tool.call", TOOL),
            entry(2, "tool.result", {"call_id": "tc_1", "name": "free_slots", "output": ["10:00"]}),
        ]
    )
    failed = reduce(
        [
            entry(1, "tool.call", TOOL),
            entry(2, "tool.result", {"call_id": "tc_1", "name": "free_slots", "error": "timeout"}),
        ]
    )
    assert (done.tools[0].status, done.tools[0].output, done.tools[0].seq) == ("done", ["10:00"], 1)
    assert (failed.tools[0].status, failed.tools[0].error) == ("failed", "timeout")


def test_a_granted_confirm_settles_the_pending_request_with_what_was_said() -> None:
    params: JsonObject = {
        "tool": "move",
        "call_id": "tc_2",
        "arguments": {},
        "audience": "sha256:a",
        "phrase": "¿Lo muevo al viernes?",
        "ttl_s": 60,
    }
    granted: JsonObject = {
        "tool": "move",
        "call_id": "tc_2",
        "audience": "sha256:a",
        "said": "vale",
        "ttl_s": 60,
    }
    state = reduce([entry(1, "confirm.request", params), entry(2, "confirm.granted", granted)])
    assert (state.confirms[0].status, state.confirms[0].said) == ("granted", "vale")


def test_a_declined_confirm_says_why_and_keeps_what_was_said_only_when_something_was() -> None:
    params: JsonObject = {
        "tool": "move",
        "call_id": "tc_3",
        "arguments": {},
        "audience": "sha256:a",
        "phrase": "¿Lo muevo?",
        "ttl_s": 60,
    }
    lapsed: JsonObject = {
        "tool": "move",
        "call_id": "tc_3",
        "audience": "sha256:a",
        "reason": "timeout",
    }
    state = reduce([entry(1, "confirm.request", params), entry(2, "confirm.declined", lapsed)])
    assert (state.confirms[0].status, state.confirms[0].reason) == ("declined", "timeout")
    assert "said" not in state.confirms[0].model_fields_set


# ── the gaps ──


def test_a_gap_with_a_snapshot_replaces_everything_and_is_remembered() -> None:
    started: JsonObject = {**LINE, "direction": "inbound", "caller": CALLER, "started_at": 1.0}
    snapshot = reduce([entry(1, "call.started", started)]).written()
    gap: JsonObject = {"from_seq": 1, "to_seq": 4, "snapshot": snapshot}
    state = reduce([entry(4, "log.gap", gap, ephemeral=True)])
    assert (state.status, state.seq) == ("active", 4)
    assert [(gap.from_seq, gap.to_seq) for gap in state.gaps] == [(1, 4)]


def test_a_gap_without_a_snapshot_only_moves_the_cursor() -> None:
    gap: JsonObject = {"from_seq": 6, "to_seq": 9, "snapshot": None}
    state = apply(initial_state(), entry(9, "log.gap", gap, ephemeral=True))
    assert (state.status, state.seq, len(state.gaps)) == ("idle", 9, 1)


# ── the metrics ──


def test_metric_blocks_are_kept_by_kind_in_the_order_they_came() -> None:
    eou: JsonObject = {
        "type": "eou_metrics",
        "timestamp": 3.0,
        "end_of_utterance_delay": 0.3,
        "transcription_delay": 0.2,
        "on_user_turn_completed_delay": 0.0,
        "speech_id": "u1",
    }
    state = reduce(
        [entry(1, "metrics.eou", eou), entry(2, "metrics.eou", {**eou, "speech_id": "u2"})]
    )
    assert [block.speech_id for block in state.metrics.eou] == ["u1", "u2"]
    assert state.metrics.llm == []


def test_every_metric_the_wire_names_has_a_block_of_its_own() -> None:
    kinds = {name.removeprefix("metrics.") for name in EVENTS if name.startswith("metrics.")}
    assert kinds == set(initial_state().metrics.written())


# ── the people ──


def test_a_supervisor_taking_over_and_releasing_leaves_the_line_with_the_agent() -> None:
    state = reduce([entry(1, "supervisor.took_over", {"by": BOSS})])
    assert state.handoff.active
    assert state.handoff.by is not None
    state = apply(state, entry(2, "supervisor.released", {"by": BOSS}))
    assert (state.handoff.active, state.handoff.by) == (False, None)


def test_a_transfer_a_supervisor_asked_for_stays_theirs_when_it_lands() -> None:
    params: JsonObject = {"by": BOSS, "to": "+34955000000"}
    state = reduce(
        [
            entry(1, "supervisor.transferred", params),
            entry(2, "call.transferred", {"to": "+34955000000", "ok": True}),
        ]
    )
    assert state.transfer is not None
    assert (state.transfer.status, state.transfer.by) == ("done", "supervisor")


def test_an_ask_for_a_person_still_open_when_the_call_ends_has_lapsed() -> None:
    ended: JsonObject = {
        "reason": "caller_hung_up",
        "ended_by": "caller",
        "ended_at": 5.0,
        "duration_s": 4.0,
    }
    state = reduce(
        [
            entry(1, "attention.requested", {"reason": "wants a person", "wait_s": 30.0}),
            entry(2, "call.ended", ended),
        ]
    )
    assert state.attention is not None
    assert (state.attention.status, state.attention.asked_at) == ("lapsed", entry(1, "x", {}).ts)


def test_an_answer_to_nobodys_ask_changes_nothing() -> None:
    state = reduce([entry(1, "attention.answered", {"ok": True, "by": BOSS})])
    assert state.attention is None


# ── the room ──


def test_a_room_fills_as_participants_join_and_the_caller_takes_the_caller_seat() -> None:
    state = reduce([entry(1, "room.opened", ROOM), entry(2, "participant.joined", SEAT)])
    assert state.room is not None
    assert state.room.caller == "sip_caller"
    seat = state.room.participants[0]
    assert (seat.joined_at, seat.speaking, seat.name) == (entry(2, "x", {}).ts, False, None)
    assert seat.attributes == {"sip.trunk": "t"}


def test_the_room_lights_a_participant_while_it_hears_them() -> None:
    lit: JsonObject = {"identity": "sip_caller", "speaking": True}
    state = reduce(
        [
            entry(1, "room.opened", ROOM),
            entry(2, "participant.joined", SEAT),
            entry(3, "participant.speaking", lit, ephemeral=True),
        ]
    )
    assert state.room is not None
    assert state.room.participants[0].speaking
    state = apply(
        state, entry(4, "participant.speaking", {**lit, "speaking": False}, ephemeral=True)
    )
    assert state.room is not None
    assert not state.room.participants[0].speaking


def test_a_participant_leaving_is_forgotten_and_the_caller_seat_empties() -> None:
    gone: JsonObject = {"identity": "sip_caller", "reason": "client_initiated"}
    state = reduce(
        [
            entry(1, "room.opened", ROOM),
            entry(2, "participant.joined", SEAT),
            entry(3, "participant.left", gone),
        ]
    )
    assert state.room is not None
    assert (state.room.participants, state.room.caller) == ([], None)


def test_a_participant_fact_before_the_room_opened_changes_nothing() -> None:
    assert reduce([entry(1, "participant.joined", SEAT)]).room is None


def test_an_outside_fact_is_kept_by_name_and_origin_and_its_cause_names_it() -> None:
    fact: JsonObject = {"name": "slot.freed", "data": {"at": "11:30"}, "source": "app"}
    moved: JsonObject = {
        "state": {"free": ["11:30"]},
        "changed": ["free"],
        "cause": {"kind": "event", "name": "slot.freed", "seq": 1},
    }
    state = reduce([entry(1, "event.received", fact), entry(2, "state.changed", moved)])
    assert [(event.seq, event.name, event.source, event.identity) for event in state.events] == [
        (1, "slot.freed", "app", None)
    ]
    assert state.app_state == {"free": ["11:30"]}


# ── what cannot be read ──

FROM_ANOTHER_VERSION = entry(7, "prompt.changed", {"region": "static", "hash": "h", "chars": 4})


def test_an_entry_this_reader_cannot_read_is_one_line_of_the_errors_list() -> None:
    state = apply(initial_state(), FROM_ANOTHER_VERSION)
    assert [error.code for error in state.errors] == [UNREADABLE]
    assert "prompt.changed at seq 7" in state.errors[0].message
    assert "\n" not in state.errors[0].message
    assert state.prompt == {}


def test_the_fold_still_moves_to_the_seq_it_could_not_read() -> None:
    state = apply(initial_state(), FROM_ANOTHER_VERSION)
    assert (state.seq, state.agent, state.call) == (7, AGENT, CALL)


def test_an_entry_of_a_type_nobody_knows_is_refused_the_same_way() -> None:
    unknown = FROM_ANOTHER_VERSION.model_copy(update={"type": "nobody.knows"})
    assert "nobody.knows at seq 7" in apply(initial_state(), unknown).errors[0].message


def test_the_entries_around_it_are_folded_as_if_it_had_not_been_there() -> None:
    started: JsonObject = {
        "channel": "web",
        "direction": "inbound",
        "from": "web_3",
        "to": AGENT,
        "caller": None,
        "started_at": 2.0,
    }
    state = reduce([FROM_ANOTHER_VERSION, entry(8, "call.started", started)])
    assert (state.status, state.seq, len(state.errors)) == ("active", 8, 1)
