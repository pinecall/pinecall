"""The app's commands on a call: what each one does, the cause it carries, and what is refused."""

import pytest

from runtime.calls.log.store import Store
from runtime.exceptions import Forbidden, ValidationError
from runtime.session.commands import apply, take
from runtime.wire.base import Command
from runtime.wire.commands import (
    AgentReply,
    AgentSay,
    CallCallback,
    CallEvent,
    CallHangup,
    CallLog,
    CallTransfer,
    PromptSet,
    SessionConfigure,
    StateSet,
    TransferVerb,
)
from runtime.wire.declaration import AgentConfig as Declared
from runtime.wire.parts import StateCauseHook, StateCauseTool
from tests.conftest import needs_the_database, until
from tests.session.conftest import (
    BOOKING,
    NOBODY,
    Box,
    a_session,
    hear,
    kinds,
    model_of,
    settled,
    supervised,
)

# ── the app's commands ──


@needs_the_database
async def test_agent_say_is_the_sessions_say_verbatim_and_enters_the_history(box: Box) -> None:
    session = a_session(box, NOBODY, ["Sí, lo dije"])
    await session.start()
    await apply(session, AgentSay(text="Su turno es el lunes."))
    await settled()
    await hear(session, "¿qué dijo?")
    sentence = [getattr(item, "text_content", "") for item in model_of(session).requests[0].items]
    assert "Su turno es el lunes." in sentence
    await session.end("caller_hung_up", "caller")


@needs_the_database
async def test_agent_reply_is_one_model_turn_guided_by_the_instruction(box: Box) -> None:
    session = a_session(box, NOBODY, ["Le confirmo el turno"])
    await session.start()
    await apply(session, AgentReply(instructions="Confirma el turno"))
    await until(lambda: len(model_of(session).requests) > 0)
    requests = model_of(session).requests
    assert len(requests) == 1
    assert "Confirma el turno" in str([getattr(item, "text_content", "") for item in requests[0].items])
    await session.end("caller_hung_up", "caller")


@needs_the_database
async def test_the_same_instructions_twice_is_not_a_rewrite(box: Box) -> None:
    session = a_session(box, NOBODY)
    await session.start()
    await apply(session, PromptSet(name="identity", text="Hola"))
    before = session.agent.instructions
    assert not session.blocks.set("identity", "Hola")
    assert session.agent.instructions == before
    await session.end("caller_hung_up", "caller")


@needs_the_database
async def test_the_view_reaches_the_model_last_and_never_touches_the_instructions(box: Box) -> None:
    session = a_session(box, NOBODY, ["ok"])
    await session.start()
    await apply(session, PromptSet(name="view", text="Turnos libres: lunes"))
    await hear(session, "¿hay turno?")
    await session.end("caller_hung_up", "caller")
    items = model_of(session).requests[0].items
    assert "Turnos libres" in str(getattr(items[-1], "text_content", ""))
    assert "Turnos libres" not in str(session.agent.instructions)


@needs_the_database
async def test_the_state_the_app_set_lands_whole_with_what_changed(box: Box, store: Store, call: str) -> None:
    session = a_session(box, NOBODY)
    await session.start()
    await apply(session, StateSet(state={"patient": {"name": "Ana Pérez"}, "step": 2}))
    await session.end("caller_hung_up", "caller")
    changed = next(entry for entry in await store.whole_of(call) if entry.type == "state.changed")
    assert changed.data["state"] == {"patient": {"name": "Ana Pérez"}, "step": 2}
    assert changed.data["changed"] == ["patient", "step"]


@needs_the_database
async def test_a_session_configure_declares_for_the_call_and_sets_its_state(box: Box, store: Store, call: str) -> None:
    session = a_session(box, NOBODY)
    await session.start()
    await apply(session, SessionConfigure(config=Declared(language="en-US"), state={"step": 1}))
    await session.end("caller_hung_up", "caller")
    assert session.call.declaration.language == "en-US"
    assert {"agent.configured", "state.changed"} <= set(await kinds(store, call))


@needs_the_database
async def test_an_event_the_app_sent_is_the_cause_of_the_next_state(box: Box, store: Store, call: str) -> None:
    session = a_session(box, BOOKING)
    await session.start()
    await apply(session, CallEvent(name="paid", data={"eur": 30}))
    await apply(session, StateSet(state={"paid": True}))
    await apply(session, StateSet(state={"paid": True, "again": 1}))
    await session.end("caller_hung_up", "caller")
    entries = await store.whole_of(call)
    received = next(entry for entry in entries if entry.type == "event.received")
    states = [entry.data for entry in entries if entry.type == "state.changed"]
    assert states[0]["cause"] == {"kind": "event", "name": "paid", "seq": received.seq}
    assert "cause" not in states[1]


@needs_the_database
async def test_every_write_an_app_authors_carries_its_cause_and_a_hook_is_its_own_kind(
    box: Box, store: Store, call: str
) -> None:
    session = a_session(box, BOOKING)
    await session.start()
    await apply(session, CallEvent(name="paid", data={"eur": 30}))
    await apply(session, StateSet(state={"a": 1}, changed=["a"], cause=StateCauseHook(kind="hook", hook="on_call")))
    book = StateCauseTool(kind="tool", tool="book", call_id="t1")
    await apply(session, StateSet(state={"a": 1, "b": 2}, changed=["b"], cause=book))
    await apply(session, StateSet(state={"a": 1, "b": 2, "c": 3}, changed=["c"], cause=book))
    await apply(session, StateSet(state={"a": 1, "b": 2, "c": 3, "d": 4}, changed=["d"]))
    await session.end("caller_hung_up", "caller")
    states = [entry.data for entry in await store.whole_of(call) if entry.type == "state.changed"]
    # The event the platform saw is spent on the first write, which the app named a hook's.
    assert [state.get("cause") for state in states] == [
        {"kind": "hook", "hook": "on_call"},
        {"kind": "tool", "tool": "book", "call_id": "t1"},
        {"kind": "tool", "tool": "book", "call_id": "t1"},
        None,
    ]


@needs_the_database
async def test_an_event_the_agent_did_not_declare_for_its_sender_is_refused(box: Box) -> None:
    session = a_session(box, BOOKING)
    await session.start()
    with pytest.raises(ValidationError, match="'clicked' is not one"):
        await apply(session, CallEvent(name="clicked", data={}))
    await session.end("caller_hung_up", "caller")


@needs_the_database
async def test_call_log_and_call_callback_are_written_where_the_call_runs(box: Box, store: Store, call: str) -> None:
    session = a_session(box, NOBODY)
    await session.start()
    await apply(session, CallLog(name="crm", data={"ticket": 7}))
    await apply(session, CallCallback(number="+59899000111", when="mañana"))
    await session.end("caller_hung_up", "caller")
    entries = {entry.type: entry.data for entry in await store.whole_of(call)}
    assert entries["custom"] == {"name": "crm", "data": {"ticket": 7}}
    back = entries["callback.requested"]
    assert (back["via"], back["call"], back["number"]) == ("agent", call, "+59899000111")


@needs_the_database
async def test_call_hangup_ends_the_call_as_the_agent(box: Box, store: Store, call: str) -> None:
    session = a_session(box, NOBODY)
    await session.start()
    await apply(session, CallHangup())
    await session.close()
    ended = next(entry for entry in await store.whole_of(call) if entry.type == "call.ended")
    assert (ended.data["reason"], ended.data["ended_by"]) == ("agent_hung_up", "agent")


@needs_the_database
async def test_the_agents_transfer_on_a_written_call_fails_as_a_transfer_and_the_call_goes_on(
    box: Box, store: Store, call: str
) -> None:
    session = a_session(box, NOBODY)
    await session.start()
    await apply(session, CallTransfer(to="+59829000000"))
    assert session.ended is None
    await session.end("caller_hung_up", "caller")
    transferred = next(entry for entry in await store.whole_of(call) if entry.type == "call.transferred")
    assert (transferred.data["to"], transferred.data["ok"]) == ("+59829000000", False)
    assert transferred.data.get("mode") is None
    assert transferred.data["error"] == "a written conversation has no line to transfer"


@needs_the_database
async def test_a_supervisors_transfer_on_a_call_with_no_room_is_refused_by_name(box: Box) -> None:
    session = a_session(box, NOBODY)
    await session.start()
    with pytest.raises(Forbidden, match="supervise transfer acts on a call's line, and this call is written"):
        await apply(session, supervised(TransferVerb(to="+59829000000")))
    await session.end("caller_hung_up", "caller")


# ── the gateway's own words on a call's stream ──


def _said(kind: str, **data: object) -> Command:
    return Command(type=kind, agent="clinica-norte", call="call_1", id=None, data=dict(data))


@needs_the_database
async def test_the_callers_hang_up_on_the_stream_ends_the_call_as_the_callers_and_is_no_apps_command(box: Box) -> None:
    session = a_session(box, NOBODY)
    await session.start()
    assert await take(session, _said("caller.hung_up")) is None
    assert session.ended == ("caller_hung_up", "caller")
    await session.close()


@needs_the_database
async def test_the_gateways_word_that_the_stages_changed_takes_them_anew_for_the_agent_it_names(box: Box) -> None:
    session = a_session(box, NOBODY)
    taken: list[str | None] = []

    async def restage(passed_to: str | None) -> None:
        taken.append(passed_to)

    assert await take(session, _said("stages.changed"), restage=restage) is None
    # A call passed to a teammate takes that agent's stages.
    assert await take(session, _said("stages.changed", agent="billing"), restage=restage) is None
    assert taken == [None, "billing"]
    # Only what runs a call at the gateway's word takes its stages: anywhere else, the word is refused.
    refused = await take(session, _said("stages.changed"))
    assert refused is not None and refused.code
