"""A written call runs on the session voice runs on: a message in, the reply out, taken up again."""

import pytest

import pinecall_runtime.session.text as text
from pinecall_runtime.agents.declaration import AgentConfig, Docs, Greeting, MemoryPolicy, ToolSpec
from pinecall_runtime.calls.store import Store
from pinecall_runtime.exceptions import Conflict
from pinecall_runtime.wire.parts import Supervisor
from tests.conftest import needs_the_database
from tests.session.conftest import Box, a_session, heard_live, kinds, model_of

AGENT = AgentConfig(slug="clinica-norte")
A_SUPERVISOR = Supervisor(id="mem_1", name="Ana")


@needs_the_database
async def test_a_message_is_answered_and_both_turns_land_in_the_log(box: Box, store: Store, call: str) -> None:
    session = a_session(box, AGENT, ["Hola", ", ¿en qué", " le ayudo?"])
    await session.start()
    sentence = await text.hear_text(session, "hola")
    await text.end_text(session, "caller_hung_up", "caller")
    assert sentence == "Hola, ¿en qué le ayudo?"
    written = await kinds(store, call)
    assert written.index("turn.user") < written.index("turn.agent")
    entries = await store.whole(call)
    agent = next(entry for entry in entries if entry.type == "turn.agent")
    assert agent.data["text"] == "Hola, ¿en qué le ayudo?"


@needs_the_database
async def test_the_reply_is_written_piece_by_piece_as_it_came(box: Box) -> None:
    seen = heard_live(box)
    session = a_session(box, AGENT, ["Hola", " qué tal"])
    await session.start()
    await text.hear_text(session, "hola")
    await text.end_text(session, "caller_hung_up", "caller")
    pieces = [entry.data["text"] for entry in seen if entry.type == "agent.transcript"]
    assert all(entry.ephemeral for entry in seen if entry.type == "agent.transcript")
    assert "".join(str(piece) for piece in pieces) == "Hola qué tal"


@needs_the_database
async def test_a_text_call_is_told_what_day_it_is_before_the_caller_says_a_word(box: Box) -> None:
    session = a_session(box, AGENT, ["Hola"])
    await session.start()
    await text.hear_text(session, "¿qué día es?")
    params = model_of(session).requests[0].items
    names = [getattr(item, "name", None) for item in params]
    assert names.index("current_date") < [getattr(item, "role", None) for item in params].index("user")
    await text.end_text(session, "caller_hung_up", "caller")


@needs_the_database
async def test_the_date_is_seeded_once_a_call_and_never_once_a_turn(box: Box) -> None:
    session = a_session(box, AGENT, ["Uno"], ["Dos"])
    await session.start()
    await text.hear_text(session, "hola")
    await text.hear_text(session, "otra vez")
    last = model_of(session).requests[-1].items
    calls = [item for item in last if getattr(item, "type", "") == "function_call"]
    assert [getattr(item, "name", "") for item in calls] == ["current_date"]
    await text.end_text(session, "caller_hung_up", "caller")


@needs_the_database
async def test_a_thread_a_supervisor_holds_logs_what_the_contact_writes_and_answers_none(
    box: Box, store: Store, call: str
) -> None:
    session = a_session(box, AGENT, ["nunca"])
    await session.start()
    session.call.taken_by = A_SUPERVISOR
    sentence = await text.hear_text(session, "¿hay alguien?")
    await text.end_text(session, "caller_hung_up", "caller")
    assert sentence == ""
    assert model_of(session).requests == []
    turns = [entry for entry in await store.whole(call) if entry.type == "turn.user"]
    assert [entry.data["text"] for entry in turns] == ["¿hay alguien?"]
    assert turns[0].data["speech_id"] == "sp_1"


@needs_the_database
async def test_a_thread_waiting_for_a_person_logs_what_the_contact_writes_and_answers_none(
    box: Box,
) -> None:
    session = a_session(box, AGENT, ["nunca"])
    await session.start()
    session.call.waiting_for_a_person = True
    assert await text.hear_text(session, "sigo acá") == ""
    assert model_of(session).requests == []
    await text.end_text(session, "caller_hung_up", "caller")


@needs_the_database
async def test_the_callers_words_are_the_query_and_the_pair_closes_the_request(box: Box) -> None:
    box.found["recall"] = {"facts": [{"text": "es alérgico a la penicilina"}]}
    agent = AgentConfig(slug="clinica-norte", memory=MemoryPolicy())
    session = a_session(box, agent, ["Anotado"], contact=None)
    await session.start()
    await text.hear_text(session, "necesito un turno para mañana")
    await text.end_text(session, "caller_hung_up", "caller")
    assert box.lookups == [("recall", {"contact": "+59899123456", "query": "necesito un turno para mañana"})]
    params = model_of(session).requests[0].items
    outputs = [getattr(item, "output", "") for item in params if getattr(item, "type", "") == "function_call_output"]
    assert any("penicilina" in str(output) for output in outputs)


@needs_the_database
async def test_a_written_caller_who_types_one_word_is_still_asked_for(box: Box) -> None:
    agent = AgentConfig(slug="clinica-norte", bases=(Docs(base="precios"),))
    session = a_session(box, agent, ["Claro"])
    await session.start()
    await text.hear_text(session, "precios")
    await text.end_text(session, "caller_hung_up", "caller")
    assert box.lookups == [("search", {"query": "precios"})]


@needs_the_database
async def test_a_turn_that_is_only_digits_asks_nothing_of_either_index(box: Box) -> None:
    agent = AgentConfig(slug="clinica-norte", memory=MemoryPolicy(), bases=(Docs(base="precios"),))
    session = a_session(box, agent, ["Gracias"])
    await session.start()
    await text.hear_text(session, "4 5 6 7")
    await text.end_text(session, "caller_hung_up", "caller")
    assert box.lookups == []


@needs_the_database
async def test_a_lookup_that_fails_is_a_recoverable_entry_and_the_turn_goes_on(
    box: Box, store: Store, call: str
) -> None:
    box.failing.add("search")
    agent = AgentConfig(slug="clinica-norte", bases=(Docs(base="precios"),))
    session = a_session(box, agent, ["Sin datos, pero sigo"])
    await session.start()
    sentence = await text.hear_text(session, "¿cuánto sale una consulta?")
    await text.end_text(session, "caller_hung_up", "caller")
    assert sentence == "Sin datos, pero sigo"
    errors = [entry.data for entry in await store.whole(call) if entry.type == "error"]
    assert errors[0]["code"] == "search_skipped"
    assert errors[0]["recoverable"] is True


@needs_the_database
async def test_hanging_up_writes_call_ended_then_hands_the_seal_what_was_used_and_said(
    box: Box, store: Store, call: str
) -> None:
    session = a_session(box, AGENT, ["Hasta luego"])
    await session.start()
    await text.hear_text(session, "chau")
    await text.end_text(session, "caller_hung_up", "caller")
    written = await kinds(store, call)
    assert written[-2:] == ["call.ended", "call.score"]
    ((usage, outcome),) = box.sealed
    assert outcome == "Hasta luego"
    assert [row.type for row in usage] == ["llm_usage"]


@needs_the_database
async def test_a_call_where_the_agent_never_spoke_is_sealed_with_no_reply(box: Box) -> None:
    session = a_session(box, AGENT)
    await session.start()
    await text.end_text(session, "caller_hung_up", "caller")
    assert box.sealed[0][1] == "no reply"


@needs_the_database
async def test_a_hangup_twice_is_a_hangup_once(box: Box, store: Store, call: str) -> None:
    session = a_session(box, AGENT)
    await session.start()
    await text.end_text(session, "caller_hung_up", "caller")
    await text.end_text(session, "caller_hung_up", "caller")
    assert (await kinds(store, call)).count("call.ended") == 1


@needs_the_database
async def test_nothing_can_be_appended_to_a_call_that_is_over(box: Box) -> None:
    session = a_session(box, AGENT)
    await session.start()
    await text.end_text(session, "caller_hung_up", "caller")
    with pytest.raises(Conflict):
        await box.log.append("custom", {"name": "late", "data": {}})


@needs_the_database
async def test_a_call_taken_up_again_has_its_history_in_the_order_it_was_written(
    box: Box, store: Store, call: str
) -> None:
    booking = AgentConfig(
        slug="clinica-norte",
        tools=(ToolSpec("book", "Book a table.", {"type": "object", "properties": {}}),),
    )
    first = a_session(
        box,
        booking,
        [{"name": "book", "arguments": {"day": "lunes"}, "call_id": "t1"}],
        ["Reservado"],
    )
    await first.start()
    await text.hear_text(first, "reserva el lunes")
    await first.call.writing.flush(5)
    taken = text.taken_up(await store.whole(call))
    kinds_in_order = [item.type for item in taken.history.items]
    assert kinds_in_order == ["message", "function_call", "function_call_output", "message"]
    assert (taken.turns, taken.last_said) == (1, "Reservado")
    assert taken.started_at == first.started_at
    await text.end_text(first, "caller_hung_up", "caller")


@needs_the_database
async def test_a_call_taken_up_counts_each_reply_once_and_numbers_on_from_the_last_speech(
    box: Box, store: Store, call: str
) -> None:
    session = a_session(box, AGENT, ["uno"])
    await session.start()
    session.call.taken_by = A_SUPERVISOR
    await text.hear_text(session, "¿hola?")
    session.call.taken_by = None
    await text.hear_text(session, "¿sigue?")
    await session.call.writing.flush(5)
    taken = text.taken_up(await store.whole(call))
    assert (taken.turns, taken.speeches) == (1, 1)
    await text.end_text(session, "caller_hung_up", "caller")


@needs_the_database
async def test_a_call_taken_up_writes_no_call_started_and_says_no_greeting(box: Box, store: Store, call: str) -> None:
    greeted = AgentConfig(slug="clinica-norte", greeting=Greeting(say="Buenas"))
    session = a_session(box, greeted)
    await text.resume_text(session, text.taken_up([]))
    await text.end_text(session, "caller_hung_up", "caller")
    written = await kinds(store, call)
    assert "call.started" not in written
    assert "turn.agent" not in written


@needs_the_database
async def test_a_round_after_a_tool_call_is_its_own_turn_of_the_agent(box: Box, store: Store, call: str) -> None:
    booking = AgentConfig(
        slug="clinica-norte",
        tools=(ToolSpec("book", "Book a table.", {"type": "object", "properties": {}}),),
    )
    session = a_session(box, booking, ["Le reservo.", {"name": "book", "call_id": "t1"}], ["Listo."])
    await session.start()
    sentence = await text.hear_text(session, "reservá")
    await text.end_text(session, "caller_hung_up", "caller")
    agent = [entry.data["text"] for entry in await store.whole(call) if entry.type == "turn.agent"]
    assert agent == ["Le reservo.", "Listo."]
    assert sentence == "Listo."


@needs_the_database
async def test_a_tool_called_in_silence_is_announced_on_every_written_turn_not_the_first_alone(
    box: Box, store: Store, call: str
) -> None:
    looking = AgentConfig(
        slug="clinica-norte",
        tools=(
            ToolSpec(
                "look",
                "Look at the agenda for a day.",
                {"type": "object", "properties": {"day": {"type": "string"}}},
                announce="Un momento, miro la agenda.",
            ),
        ),
    )
    session = a_session(
        box,
        looking,
        ["Buenas, ¿qué día le viene bien?"],
        [{"name": "look", "arguments": {"day": "lunes"}, "call_id": "t1"}],
        ["El lunes hay hueco a las nueve."],
    )
    await session.start()
    await text.hear_text(session, "hola")
    await text.hear_text(session, "¿qué hay el lunes?")
    await text.end_text(session, "caller_hung_up", "caller")
    agent = [entry.data["text"] for entry in await store.whole(call) if entry.type == "turn.agent"]
    assert agent == [
        "Buenas, ¿qué día le viene bien?",
        "Un momento, miro la agenda.",
        "El lunes hay hueco a las nueve.",
    ]
