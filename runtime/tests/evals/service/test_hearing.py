"""Tests for how a simulated spoken call was heard: the agent's log against what its caller really said."""

from runtime.evals.service.hearing import Said, count_changes, error_rate, measure
from runtime.kit.text import JsonObject, words_of
from runtime.wire.base import Entry

CALL = "call_1"


def an_entry(seq: int, kind: str, data: JsonObject) -> Entry:
    return Entry(seq=seq, ts=float(seq), call=CALL, agent="front-desk", type=kind, ephemeral=False, data=data)


def a_reply(seq: int, text: str, began: float, ended: float, *, interrupted: bool = False) -> Entry:
    """One reply of the agent, on the line from `began` to `ended`."""
    metrics: JsonObject = {"started_speaking_at": began, "stopped_speaking_at": ended}
    data: JsonObject = {"speech_id": f"s{seq}", "text": text, "interrupted": interrupted, "metrics": metrics}
    return an_entry(seq, "turn.agent", data)


def a_heard(seq: int, text: str, began: float, ended: float) -> Entry:
    """One turn the agent heard, from `began` to `ended`."""
    metrics: JsonObject = {"started_speaking_at": began, "stopped_speaking_at": ended}
    return an_entry(seq, "turn.user", {"speech_id": f"u{seq}", "text": text, "metrics": metrics})


def test_two_transcripts_are_compared_by_their_words_alone() -> None:
    assert words_of("Sí, confírmemela — ¡gracias!") == ["sí", "confírmemela", "gracias"]
    assert count_changes(["book", "me", "tuesday"], ["book", "me", "thursday"]) == 1
    assert count_changes(["book", "me"], ["please", "book", "me", "now"]) == 2
    assert error_rate(["book", "me", "tuesday", "please"], ["book", "me", "thursday", "please"]) == 0.25
    assert error_rate([], ["anything"]) is None


def test_a_clean_call_was_heard_whole_and_answered_every_time() -> None:
    """Every line heard as said and answered after it: nothing missed, invented or talked over."""
    said = [Said("line", "Book me Tuesday.", 10.0, 12.0), Said("line", "Yes, at nine.", 20.0, 21.0)]
    log = [
        a_heard(1, "Book me Tuesday.", 10.1, 12.1),
        a_reply(2, "Tuesday at nine or ten?", 13.0, 16.0),
        a_heard(3, "Yes, at nine.", 20.1, 21.1),
        a_reply(4, "Booked.", 22.5, 23.5),
    ]
    heard = measure(log, said)
    assert (heard.lines, heard.unanswered, heard.phantom_turns) == (2, 0, 0)
    assert (heard.cut_by_the_room, heard.cut_by_a_murmur, heard.talked_over) == (0, 0, 0)
    assert heard.word_error_rate == 0.0
    assert heard.reply_s == 1.25
    assert heard.slow_reply_s == 1.5


# The call that showed why these are measured (2026-11-09): a café heard as the caller, an agent that
# answered twice in three minutes, and every judge holding, since a judge reads the transcript alone.
def test_a_room_taken_for_the_caller_is_a_turn_nobody_said_and_a_reply_nobody_cut() -> None:
    """A turn heard while the caller said nothing is the room's; a reply cut off then was cut by the room."""
    said = [Said("line", "Book me Tuesday.", 10.0, 12.0)]
    log = [
        a_heard(1, "book me tuesday el equipo local venció", 10.1, 12.1),
        a_reply(2, "Tuesday at", 13.0, 14.0, interrupted=True),
        a_heard(3, "por dos goles a uno", 30.0, 40.0),
    ]
    heard = measure(log, said)
    assert heard.phantom_turns == 1
    assert heard.cut_by_the_room == 1
    assert heard.word_error_rate is not None and heard.word_error_rate > 1.0


def test_a_reply_the_caller_cut_in_on_is_the_callers_doing_and_a_murmurs_is_told_apart() -> None:
    """A caller's own line over a reply is no fault of the room; a murmur that stops the agent is its own count."""
    said = [
        Said("line", "Book me Tuesday.", 10.0, 12.0),
        Said("line", "Wait, Thursday.", 14.5, 15.5, cut_in=True),
        Said("murmur", "mm-hmm", 21.0, 21.4),
    ]
    log = [
        a_reply(1, "Tuesday at", 13.0, 14.8, interrupted=True),
        a_reply(2, "Thursday at nine, then, or", 17.0, 21.5, interrupted=True),
    ]
    heard = measure(log, said)
    assert (heard.cut_by_the_room, heard.cut_by_a_murmur) == (0, 1)


def test_a_line_with_no_reply_before_the_next_is_unanswered_and_a_reply_begun_inside_one_talked_over_it() -> None:
    """The agent that said nothing to a line missed it; the one that began mid-line spoke over the caller."""
    said = [
        Said("line", "I need to move my appointment to another day.", 10.0, 16.0),
        Said("line", "Hello?", 30.0, 31.0),
        Said("line", "Are you there?", 40.0, 41.0),
    ]
    log = [a_reply(1, "Sure, which", 13.0, 14.0), a_reply(2, "Yes, I am here.", 42.0, 43.0)]
    heard = measure(log, said)
    assert heard.talked_over == 1
    assert heard.unanswered == 2
    assert heard.reply_s == 1.0


def test_a_caller_that_said_nothing_has_no_rate_and_every_turn_heard_is_the_rooms() -> None:
    """A silent caller on a noisy line: whatever the agent heard, nobody said."""
    heard = measure([a_heard(1, "resumen deportivo", 5.0, 9.0)], [])
    assert (heard.lines, heard.phantom_turns, heard.word_error_rate, heard.reply_s) == (0, 1, None, None)
