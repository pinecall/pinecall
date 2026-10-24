"""What a participant reads of a call's log: the public projection, row by row."""

from pinecall_runtime.calls.readers import project_entry
from pinecall_runtime.wire.base import Entry


def _said(word: str, start: float) -> Entry:
    data = {"speech_id": "speech_1", "text": word, "final": False, "start": start, "language": "en"}
    return Entry(seq=7, ts=1.0, call="call_1", agent="pip", type="agent.transcript", ephemeral=True, data=data)


def test_a_participant_reads_the_second_each_word_of_the_reply_is_said_at() -> None:
    projected = project_entry(_said("Pricing", 0.03), "public", None)

    assert projected is not None
    assert projected["data"] == {"speech_id": "speech_1", "text": "Pricing", "final": False, "start": 0.03}


def test_a_participant_never_reads_whose_agent_or_call_it_is() -> None:
    projected = project_entry(_said("Pricing", 0.03), "public", None)

    assert projected is not None
    assert set(projected) == {"seq", "ts", "type", "ephemeral", "data"}
