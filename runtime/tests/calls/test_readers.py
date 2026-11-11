"""What a participant reads of a call's log: the public projection, row by row."""

from pinecall_runtime.agents.declaration import AgentConfig
from pinecall_runtime.calls.readers import Declaring, project_entry
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


async def test_a_stream_begun_before_its_call_opened_reads_what_is_public_once_it_has() -> None:
    """A page follows from the mint: the declaration is asked for again at each entry until the call has one."""
    declared = AgentConfig(slug="pip", state_fields={"screen": "public"})
    answers = iter([None, declared])

    async def late() -> AgentConfig | None:
        return next(answers)

    declaring = Declaring(None, late)
    data = {"state": {"screen": [], "plan": "pro"}, "changed": ["screen"]}
    changed = Entry(seq=9, ts=1.0, call="call_1", agent="pip", type="state.changed", ephemeral=False, data=data)
    before = project_entry(changed, "public", await declaring.now())
    after = project_entry(changed, "public", await declaring.now())

    assert before is not None and before["data"] == {"state": {}, "changed": []}
    assert after is not None and after["data"] == {"state": {"screen": []}, "changed": ["screen"]}
    assert await declaring.now() is declared


async def test_a_stream_stops_asking_for_a_declaration_its_call_never_had() -> None:
    asked = 0

    async def late() -> AgentConfig | None:
        nonlocal asked
        asked += 1
        return None

    declaring = Declaring(None, late, tries=2)
    assert [await declaring.now() for _ in range(4)] == [None, None, None, None]
    assert asked == 2
