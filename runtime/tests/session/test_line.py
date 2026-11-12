"""Who has a call's line: a hold, a person awaited, a supervisor's verbs, and the agent mute and deaf under them."""

import asyncio

import pytest

from runtime.calls.log.store import Store
from runtime.exceptions import Forbidden, ValidationError
from runtime.session.commands import apply
from runtime.session.prompt import A_RELEASE
from runtime.session.session import Place
from runtime.wire.commands import (
    CallAttention,
    CallHold,
    CallUnhold,
    EndVerb,
    ReleaseVerb,
    SayVerb,
    TakeoverVerb,
    TransferVerb,
    WhisperVerb,
)
from tests.conftest import needs_the_database, until
from tests.fakes.livekit import Server, Speaker
from tests.session.conftest import (
    A_SUPERVISOR,
    NOBODY,
    Box,
    a_room,
    a_session,
    kinds,
    model_of,
    settled,
    spoken_call,
    supervised,
)

# The old call's `a_person_has_the_line`: a supervisor holds the line, or one is awaited.
AWAITED_OR_TAKEN = frozenset({"attention", "supervisor"})


# ── a person on the line ──


@needs_the_database
async def test_holding_a_call_writes_the_line_once_and_giving_it_back_writes_it_again(
    box: Box, store: Store, call: str
) -> None:
    session = a_session(box, NOBODY)
    await session.start()
    await apply(session, CallHold())
    await apply(session, CallHold())
    await apply(session, CallUnhold())
    await session.end("caller_hung_up", "caller")
    lines = [entry.data for entry in await store.whole_of(call) if entry.type == "call.line"]
    assert lines == [{"held": True, "muted": False}, {"held": False, "muted": False}]


@needs_the_database
async def test_an_ask_puts_the_caller_on_hold_and_says_what_a_supervisor_is_wanted_for(
    box: Box, store: Store, call: str
) -> None:
    session = a_session(box, NOBODY)
    await session.start()
    await apply(session, CallAttention(reason="quiere hablar con un médico", wait_s=30))
    assert session.line.reasons & AWAITED_OR_TAKEN
    with pytest.raises(ValidationError, match="already waiting"):
        await apply(session, CallAttention(reason="otra vez", wait_s=30))
    await session.end("caller_hung_up", "caller")
    entries = await store.whole_of(call)
    found = next(entry for entry in entries if entry.type == "attention.requested")
    assert found.data == {"reason": "quiere hablar con un médico", "wait_s": 30.0}
    assert [entry.data["held"] for entry in entries if entry.type == "call.line"] == [True]


@needs_the_database
async def test_a_supervisor_taking_the_line_answers_the_ask(box: Box, store: Store, call: str) -> None:
    session = a_session(box, NOBODY)
    await session.start()
    await apply(session, CallAttention(reason="ayuda", wait_s=30))
    await apply(session, supervised(TakeoverVerb()))
    await session.end("caller_hung_up", "caller")
    entries = await store.whole_of(call)
    answered = next(entry for entry in entries if entry.type == "attention.answered")
    assert answered.data["ok"] is True
    assert answered.data["by"] == {"id": "mem_1", "name": "Ana"}
    assert session.line.taken_by == A_SUPERVISOR
    assert "attention" not in session.line.reasons


@needs_the_database
async def test_a_wait_nobody_answered_gives_the_line_back_to_the_agent(box: Box, store: Store, call: str) -> None:
    session = a_session(box, NOBODY)
    await session.start()
    await apply(session, CallAttention(reason="ayuda", wait_s=0.05))
    await asyncio.sleep(0.2)
    await session.end("caller_hung_up", "caller")
    entries = await store.whole_of(call)
    answered = next(entry for entry in entries if entry.type == "attention.answered")
    assert (answered.data["ok"], answered.data["error"]) == (
        False,
        "nobody took the line within 0.05s",
    )
    assert [entry.data["held"] for entry in entries if entry.type == "call.line"] == [True, False]
    assert not session.line.reasons & AWAITED_OR_TAKEN


@needs_the_database
async def test_say_writes_who_asked_before_the_agent_says_a_word(box: Box, store: Store, call: str) -> None:
    session = a_session(box, NOBODY)
    await session.start()
    await apply(session, supervised(SayVerb(text="Un momento, por favor.")))
    await settled()
    await session.end("caller_hung_up", "caller")
    written = await kinds(store, call)
    assert written.index("supervisor.said") < written.index("turn.agent")


@needs_the_database
async def test_a_whisper_lands_in_the_history_and_asks_for_the_next_turn(box: Box, store: Store, call: str) -> None:
    session = a_session(box, NOBODY, ["Le ofrezco el martes"])
    await session.start()
    await apply(session, supervised(WhisperVerb(text="ofrecele el martes")))
    await settled()
    await session.end("caller_hung_up", "caller")
    (request,) = model_of(session).requests
    notes = [str(getattr(item, "text_content", "")) for item in request.items]
    assert any("ofrecele el martes" in note for note in notes)
    assert "ofrecele" not in str(session.agent.instructions)
    assert "supervisor.whispered" in await kinds(store, call)


@needs_the_database
async def test_a_whisper_while_a_human_holds_the_line_never_talks_over_them(box: Box) -> None:
    session = a_session(box, NOBODY, ["nunca"])
    await session.start()
    await apply(session, supervised(TakeoverVerb()))
    await apply(session, supervised(WhisperVerb(text="nada")))
    await settled()
    assert model_of(session).requests == []
    await session.end("caller_hung_up", "caller")


@needs_the_database
async def test_a_second_takeover_is_refused_and_names_who_holds_the_line(box: Box) -> None:
    session = a_session(box, NOBODY)
    await session.start()
    await apply(session, supervised(TakeoverVerb()))
    with pytest.raises(ValidationError, match="mem_1 already holds the line"):
        await apply(session, supervised(TakeoverVerb()))
    await session.end("caller_hung_up", "caller")


@needs_the_database
async def test_a_release_gives_the_line_back_with_a_note_that_never_guesses(box: Box) -> None:
    session = a_session(box, NOBODY, ["¿Seguimos?"])
    await session.start()
    await apply(session, supervised(TakeoverVerb()))
    await apply(session, supervised(ReleaseVerb()))
    await settled()
    await session.end("caller_hung_up", "caller")
    assert session.line.taken_by is None
    notes = [str(getattr(item, "text_content", "")) for item in model_of(session).requests[0].items]
    assert A_RELEASE in notes
    assert "Do not guess" in A_RELEASE


@needs_the_database
async def test_a_release_nobody_asked_for_is_refused_and_writes_nothing(box: Box, store: Store, call: str) -> None:
    session = a_session(box, NOBODY)
    await session.start()
    with pytest.raises(ValidationError, match="nobody holds the line"):
        await apply(session, supervised(ReleaseVerb()))
    await session.end("caller_hung_up", "caller")
    assert "supervisor.released" not in await kinds(store, call)


@needs_the_database
async def test_the_end_verb_hangs_up_as_the_supervisor_and_never_as_the_agent(
    box: Box, store: Store, call: str
) -> None:
    session = a_session(box, NOBODY)
    await session.start()
    await apply(session, supervised(EndVerb(reason="spam")))
    await session.close()
    entries = {entry.type: entry.data for entry in await store.whole_of(call)}
    assert entries["supervisor.ended"]["reason"] == "spam"
    assert (entries["call.ended"]["reason"], entries["call.ended"]["ended_by"]) == (
        "supervisor_ended",
        "supervisor",
    )


@needs_the_database
async def test_a_transfer_on_a_written_call_is_refused_before_anything_is_written(
    box: Box, store: Store, call: str
) -> None:
    session = a_session(box, NOBODY)
    await session.start()
    with pytest.raises(Forbidden):
        await apply(session, supervised(TransferVerb(to="+59829000000")))
    await session.close()
    assert "supervisor.transferred" not in await kinds(store, call)


# ── the line ──


@needs_the_database
async def test_a_held_call_leaves_the_agent_neither_speaking_nor_hearing(box: Box) -> None:
    session = a_session(box, NOBODY)
    await session.start()
    await apply(session, CallHold())
    assert (session.live.input.audio_enabled, session.live.output.audio_enabled) == (False, False)
    await session.end("caller_hung_up", "caller")


@needs_the_database
async def test_a_takeover_cuts_the_sentence_and_leaves_the_agent_mute_and_deaf(
    box: Box, store: Store, call: str
) -> None:
    session = spoken_call(box, NOBODY)
    speaker = Speaker()
    session.live.output.audio = speaker
    await session.start()
    session.live.say("Le leo las condiciones de la reserva, que son bastante largas.")
    await until(lambda: speaker.playing)
    await apply(session, supervised(TakeoverVerb()))
    await until(lambda: speaker.cut == 1)
    assert (session.live.input.audio_enabled, session.live.output.audio_enabled) == (False, False)
    await session.end("caller_hung_up", "caller")
    assert "supervisor.took_over" in await kinds(store, call)


# Each reason the line is not the agent's is added and taken away alone (`session/line.py`): a
# supervisor who takes a held line stops its melody, and the app's hold stands under them, so the
# line goes back on hold, not to the agent, when they release it. Until 2026-11 the takeover ended
# the app's hold.
@needs_the_database
async def test_a_supervisor_taking_a_held_line_stops_its_melody_and_the_apps_hold_stands_under_them(
    box: Box, store: Store, call: str
) -> None:
    session = a_session(box, NOBODY)
    await session.start()
    await apply(session, CallHold())
    await apply(session, supervised(TakeoverVerb()))
    await session.end("caller_hung_up", "caller")
    lines = [entry.data["held"] for entry in await store.whole_of(call) if entry.type == "call.line"]
    assert lines == [True, False]
    assert session.line.taken_by == A_SUPERVISOR
    assert session.line.reasons == {"hold", "supervisor"}


@needs_the_database
async def test_a_seat_in_the_room_is_never_handed_the_session_itself(box: Box, server: Server) -> None:
    """Hosted, livekit sends every seat the raw turns and the tools, and the prompt to one that asks."""
    session = spoken_call(box, NOBODY, server=server)
    where = session.room
    assert where is not None
    await session.start()
    # livekit's session host listens on this topic; registering it again would raise had it started.
    where.room.register_byte_stream_handler("lk.agent.session", lambda _reader, _identity: None)
    await session.close()


@needs_the_database
async def test_every_one_of_the_six_verbs_lands_in_the_callers_log(
    box: Box, store: Store, call: str, server: Server
) -> None:
    session = spoken_call(box, NOBODY, server=server)
    await session.start()
    for verb in (
        SayVerb(text="Un momento"),
        WhisperVerb(text="ofrecé el martes"),
        TakeoverVerb(),
        ReleaseVerb(),
    ):
        await apply(session, supervised(verb))
    await apply(session, supervised(TransferVerb(to="+59829000000", mode="cold")))
    await apply(session, supervised(EndVerb(reason="listo")))
    await session.close()
    written = await kinds(store, call)
    for kind in (
        "supervisor.said",
        "supervisor.whispered",
        "supervisor.took_over",
        "supervisor.released",
        "supervisor.transferred",
        "supervisor.ended",
    ):
        assert kind in written


@needs_the_database
async def test_a_transfer_is_written_here_and_finished_by_the_transfer_applier(
    box: Box, store: Store, call: str, server: Server
) -> None:
    session = a_session(box, NOBODY, place_of=lambda call: Place(room=a_room(box, call, server)))
    await session.start()
    await apply(session, supervised(TransferVerb(to="+59829000000")))
    await session.close()
    entries = await store.whole_of(call)
    written = [entry.type for entry in entries]
    assert written.index("supervisor.transferred") < written.index("call.transferred")
    found = next(entry for entry in entries if entry.type == "supervisor.transferred")
    assert found.data["mode"] == "cold"
    ended = next(entry for entry in entries if entry.type == "call.ended")
    assert ended.data["reason"] == "transferred"
