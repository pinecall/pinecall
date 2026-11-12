"""Tests for the livekit Agent the session runs: what its ears let through, what a run keeps."""

import asyncio
import time
from pathlib import Path

from livekit.agents import (
    AgentStateChangedEvent,
    SpeechCreatedEvent,
    stt,
)
from livekit.agents.utils import http_context
from livekit.agents.voice import ModelSettings, SpeechHandle

from runtime.agents.declaration import Declaration, Docs, ToolSpec
from runtime.calls.log.store import Store
from runtime.enums import Channel
from runtime.exceptions import ServiceUnavailable
from runtime.kit.text import Json, JsonObject
from runtime.providers.stage import Pipeline, Running
from runtime.session.agent import LLM_TIMEOUT, MODEL_LATE
from runtime.session.call import Call, ToolUse
from runtime.session.commands import CallCommand, apply
from runtime.session.hold import HoldMusic
from runtime.session.session import Place, Session
from runtime.session.text import text_session
from runtime.session.voice import voice_session
from runtime.wire.commands import AgentReply, AgentSay, CallHangup, CallHold, StateSet, ToolsSet
from runtime.wire.parts import ToolResult
from runtime.wire.parts import ToolSpec as WiredTool
from tests.conftest import needs_the_database, until
from tests.fakes.acme import ACME
from tests.fakes.livekit import Player, Speaker
from tests.fakes.livekit import Room as AnOfflineRoom
from tests.session.conftest import (
    BOOKING,
    LOOKING,
    NOBODY,
    POINTING,
    TALKING,
    Box,
    a_session,
    context_of,
    hear,
    kinds,
    model_of,
    no_audio,
    output_of,
    settled,
    spoken_call,
)


# The ears hear agreement over the agent's voice: it never reaches the model, and what takes the floor does.
@needs_the_database
async def test_a_backchannel_over_the_agents_voice_never_reaches_the_model(box: Box) -> None:
    session = spoken_call(box, NOBODY, hears=("sí, claro", "sí, pero el martes no puedo"))
    await session.start()
    # The ears open the job's HTTP session, as a vendor's do: outside a job, the test opens it.
    async with http_context.open():
        session.live.emit("agent_state_changed", AgentStateChangedEvent(old_state="thinking", new_state="speaking"))
        over_the_agent = [event async for event in session.agent.stt_node(no_audio(), ModelSettings())]
        session.live.emit("agent_state_changed", AgentStateChangedEvent(old_state="speaking", new_state="listening"))
        after_it = [event async for event in session.agent.stt_node(no_audio(), ModelSettings())]
    await session.close()
    finals = [event for event in over_the_agent if event.type is stt.SpeechEventType.FINAL_TRANSCRIPT]
    assert [event.alternatives[0].text for event in finals] == ["sí, pero el martes no puedo"]
    assert len([event for event in after_it if event.type is stt.SpeechEventType.FINAL_TRANSCRIPT]) == 2


@needs_the_database
async def test_a_call_an_eval_run_opened_keeps_every_request_the_model_was_sent(box: Box) -> None:
    session = a_session(box, NOBODY, ["hola"], ["adiós"], run="run_1")
    await session.start()
    await hear(session, "buenas")
    await hear(session, "gracias")
    await session.end("caller_hung_up", "caller")
    requests = session.call.requests
    assert len(requests) == 2
    assert {"system", "tools", "messages"} <= set(requests[0])
    assert "buenas" in str(requests[0]["messages"])


@needs_the_database
async def test_a_real_callers_call_keeps_no_request(box: Box) -> None:
    session = a_session(box, NOBODY, ["hola"])
    await session.start()
    await hear(session, "buenas")
    await session.end("caller_hung_up", "caller")
    assert session.call.requests == []


# ── a slow model ──


@needs_the_database
async def test_a_model_past_the_agents_deadline_is_cut_and_the_caller_asked_to_say_it_again(
    box: Box, store: Store, call: str
) -> None:
    config = Declaration(slug="clinica-norte", language="es-ES", llm_timeout_s=0.05)
    session = a_session(box, config, ["tarde"])
    model_of(session).thinks_s = 5.0
    await session.start()
    sentence = await hear(session, "hola")
    await session.end("caller_hung_up", "caller")
    assert sentence == MODEL_LATE["es"]
    (cut,) = [entry.data for entry in await store.whole_of(call) if entry.type == "error"]
    assert (cut["code"], cut["recoverable"]) == (LLM_TIMEOUT, True)
    assert "0.05s" in str(cut["message"])
    assert len(model_of(session).requests) == 1


@needs_the_database
async def test_an_agent_with_no_deadline_of_its_own_waits_for_a_slow_model_under_the_default(
    box: Box, store: Store, call: str
) -> None:
    session = a_session(box, NOBODY, ["por fin"])
    model_of(session).thinks_s = 0.2
    await session.start()
    sentence = await hear(session, "hola")
    await session.end("caller_hung_up", "caller")
    assert sentence == "por fin"
    assert "error" not in await kinds(store, call)


@needs_the_database
async def test_the_wait_for_a_slow_model_plays_the_melody_and_its_first_word_stops_it(
    box: Box,
) -> None:
    player = Player()
    melody = HoldMusic(Path("hold.ogg"), AnOfflineRoom("call_1"), player, after_s=0.01)
    session = a_session(box, NOBODY, ["listo"], place_of=lambda _call: Place(melody=melody))
    model_of(session).thinks_s = 0.2
    await session.start()
    await hear(session, "hola")
    await session.end("caller_hung_up", "caller")
    assert player.played == [("hold.ogg", True)]
    assert all(handle.done() for handle in player.handles)
    assert melody.running == 0


@needs_the_database
async def test_a_model_that_answers_inside_the_grace_plays_nothing(box: Box) -> None:
    player = Player()
    melody = HoldMusic(Path("hold.ogg"), AnOfflineRoom("call_1"), player, after_s=5.0)
    session = a_session(box, NOBODY, ["ya"], place_of=lambda _call: Place(melody=melody))
    await session.start()
    await hear(session, "hola")
    await session.end("caller_hung_up", "caller")
    assert player.played == []
    assert (melody.running, melody.pending) == (0, None)


@needs_the_database
async def test_the_agents_turn_is_over_when_its_speech_is_done_and_not_when_its_state_says_listening(
    box: Box, store: Store, call: str
) -> None:
    session = a_session(box, NOBODY)
    await session.start()
    handle = SpeechHandle.create()
    session.live.emit(
        "speech_created", SpeechCreatedEvent(user_initiated=False, source="generate_reply", speech_handle=handle)
    )
    # livekit says "listening" between a sentence and a tool already done: the reply goes on after it.
    session.live.emit("agent_state_changed", AgentStateChangedEvent(old_state="speaking", new_state="listening"))
    await settled()
    assert "agent.waiting" not in await kinds(store, call)
    handle._mark_done()  # pyright: ignore[reportPrivateUsage]  # livekit marks it so when the reply, tools and all, is done
    await settled()
    await session.end("caller_hung_up", "caller")
    waiting = [entry.data for entry in await store.whole_of(call) if entry.type == "agent.waiting"]
    assert waiting == [{"speech_id": handle.id, "interrupted": False}]


# ── tools ──


@needs_the_database
async def test_a_tool_round_trips_through_the_platform_and_the_model_reads_its_answer(
    box: Box,
) -> None:
    box.answers["book"] = ToolResult(call_id="t1", name="book", output={"table": "mesa 4"})
    session = a_session(box, BOOKING, [{"name": "book", "arguments": {"day": "lunes"}, "call_id": "t1"}], ["Listo"])
    await session.start()
    sentence = await hear(session, "reserva el lunes")
    await session.end("caller_hung_up", "caller")
    assert [(use.name, use.arguments) for use in box.used] == [("book", {"day": "lunes"})]
    assert '"table": "mesa 4"' in output_of(session, "t1").output
    assert sentence == "Listo"


@needs_the_database
async def test_a_confirm_tool_reads_back_what_was_done_before_the_model_answers(
    box: Box, store: Store, call: str
) -> None:
    box.answers["book"] = ToolResult(call_id="t1", name="book", output={"table": "mesa 4"})
    session = a_session(
        box,
        BOOKING,
        [{"name": "book", "arguments": {"day": "lunes"}, "call_id": "t1"}],
        ["Algo más?"],
    )
    await session.start()
    await hear(session, "reserva el lunes")
    await session.end("caller_hung_up", "caller")
    agent = [entry.data["text"] for entry in await store.whole_of(call) if entry.type == "turn.agent"]
    assert agent[0] == "Reservado para el lunes, mesa 4 {{result.missing}}."
    history = [getattr(item, "text_content", "") for item in model_of(session).requests[1].items]
    assert agent[0] in history


@needs_the_database
async def test_a_tool_is_announced_as_it_starts_when_the_model_called_it_in_silence(
    box: Box, store: Store, call: str
) -> None:
    session = a_session(
        box,
        LOOKING,
        [{"name": "look", "arguments": {"day": "lunes"}, "call_id": "t1"}],
        ["El lunes hay hueco a las nueve."],
    )
    await session.start()
    await hear(session, "¿qué hay el lunes?")
    await session.end("caller_hung_up", "caller")
    agent = [entry.data["text"] for entry in await store.whole_of(call) if entry.type == "turn.agent"]
    assert agent == ["Un momento, miro la agenda.", "El lunes hay hueco a las nueve."]


@needs_the_database
async def test_a_tool_that_runs_long_says_its_delayed_line_at_its_moment(box: Box, store: Store, call: str) -> None:
    """Announced at the start, the wait's line after `delayed_after_s`, then the model's answer."""
    answering = box.run_tool

    async def slowly(use: ToolUse, speech: str | None) -> ToolResult:
        await asyncio.sleep(0.2)
        return await answering(use, speech)

    session = a_session(
        box, TALKING, [{"name": "look", "arguments": {"day": "lunes"}, "call_id": "t1"}], ["El lunes hay hueco."]
    )
    session.call.platform = box.through(slowly)
    await session.start()
    await hear(session, "¿qué hay el lunes?")
    await session.end("caller_hung_up", "caller")
    agent = [entry.data["text"] for entry in await store.whole_of(call) if entry.type == "turn.agent"]
    assert agent == ["Un momento, miro la agenda.", "Sigo buscando, un segundo.", "El lunes hay hueco."]


@needs_the_database
async def test_a_quick_tool_never_says_its_delayed_line(box: Box, store: Store, call: str) -> None:
    """The reminder is cancelled with the answer: nothing of the wait is said."""
    session = a_session(
        box, TALKING, [{"name": "look", "arguments": {"day": "lunes"}, "call_id": "t1"}], ["El lunes hay hueco."]
    )
    await session.start()
    await hear(session, "¿qué hay el lunes?")
    await asyncio.sleep(0.1)
    await session.end("caller_hung_up", "caller")
    agent = [entry.data["text"] for entry in await store.whole_of(call) if entry.type == "turn.agent"]
    assert agent == ["Un momento, miro la agenda.", "El lunes hay hueco."]


@needs_the_database
async def test_a_tool_that_failed_says_its_failed_line_before_the_model_answers(
    box: Box, store: Store, call: str
) -> None:
    """The app's error is the model's to read, after the caller heard the tool's own line for it."""
    box.answers["look"] = ToolResult(call_id="t1", name="look", error="the agenda did not answer")
    session = a_session(
        box, TALKING, [{"name": "look", "arguments": {"day": "lunes"}, "call_id": "t1"}], ["Disculpe, reintento."]
    )
    await session.start()
    await hear(session, "¿qué hay el lunes?")
    await session.end("caller_hung_up", "caller")
    agent = [entry.data["text"] for entry in await store.whole_of(call) if entry.type == "turn.agent"]
    assert agent == ["Un momento, miro la agenda.", "No pude consultar la agenda ahora mismo.", "Disculpe, reintento."]
    read = [getattr(item, "output", None) for item in model_of(session).requests[-1].items]
    assert "the agenda did not answer" in read


@needs_the_database
async def test_a_quiet_tool_runs_and_the_model_is_asked_for_no_second_answer(box: Box, store: Store, call: str) -> None:
    session = a_session(
        box,
        POINTING,
        ["Here are the prices.", {"name": "point", "arguments": {"ref": "e12"}, "call_id": "t1"}],
        ["Here are the prices, again."],
    )
    await session.start()
    await hear(session, "where are the prices?")
    await session.end("caller_hung_up", "caller")
    entries = await store.whole_of(call)
    assert [entry.data["text"] for entry in entries if entry.type == "turn.agent"] == ["Here are the prices."]
    assert [entry.data["name"] for entry in entries if entry.type == "tool.result"] == ["point"]
    assert len(model_of(session).requests) == 1


@needs_the_database
async def test_a_quiet_tool_called_in_silence_is_answered_so_the_move_is_said(
    box: Box, store: Store, call: str
) -> None:
    session = a_session(
        box,
        POINTING,
        [{"name": "point", "arguments": {"ref": "e12"}, "call_id": "t1"}],
        ["Here are the prices."],
    )
    await session.start()
    await hear(session, "where are the prices?")
    await session.end("caller_hung_up", "caller")
    entries = await store.whole_of(call)
    assert [entry.data["text"] for entry in entries if entry.type == "turn.agent"] == ["Here are the prices."]
    assert len(model_of(session).requests) == 2


CHAINED_IN_SILENCE: tuple[list[Json], ...] = (
    [{"name": "point", "arguments": {"ref": "e12"}, "call_id": "t1"}],
    [{"name": "point", "arguments": {"ref": "e13"}, "call_id": "t2"}],
    ["Here are the prices."],
)


@needs_the_database
async def test_quiet_tools_chained_in_silence_end_on_the_models_own_words(box: Box, store: Store, call: str) -> None:
    session = a_session(box, POINTING, *CHAINED_IN_SILENCE)
    await session.start()
    await hear(session, "where are the prices?")
    await session.end("caller_hung_up", "caller")
    entries = await store.whole_of(call)
    last = model_of(session).requests[-1]
    assert [entry.data["text"] for entry in entries if entry.type == "turn.agent"] == ["Here are the prices."]
    assert (last.tool_choice, last.tools) == ("auto", ["point"])


# Past the steps the runtime allows, livekit asks for words: that request is offered no tool, so a
# model that would call one anyway cannot, and says something.
@needs_the_database
async def test_tools_chained_past_the_steps_allowed_end_on_a_step_offered_no_tool(
    box: Box, store: Store, call: str
) -> None:
    assert box.log.call is not None
    script: JsonObject = {"replies": list(CHAINED_IN_SILENCE)}
    session = text_session(
        Call(context_of(box.log.call), POINTING, box), Running(ACME, "a-key", options=script), Place(), tool_steps=1
    )
    await session.start()
    await hear(session, "where are the prices?")
    await session.end("caller_hung_up", "caller")
    entries = await store.whole_of(call)
    last = model_of(session).requests[-1]
    assert [entry.data["text"] for entry in entries if entry.type == "turn.agent"] == ["Here are the prices."]
    assert (last.tool_choice, last.tools) == ("none", [])


FINISH = ToolSpec("finish", "End the call once the caller is served.", {"type": "object", "properties": {}})
FINISHING = Declaration(slug="clinica-norte", tools=(FINISH,))
HOLD = ToolSpec(
    "hold_line", "Put the caller on hold while something is looked up.", {"type": "object", "properties": {}}
)
HOLDING = Declaration(slug="clinica-norte", tools=(HOLD,))


def commanding_through(box: Box, config: Declaration, command: CallCommand, replies: list[list[Json]]) -> Session:
    """A written session whose one tool sends the app's command from inside its run, before it answers."""
    assert box.log.call is not None

    async def run(use: ToolUse, speech: str | None) -> ToolResult:
        await apply(session, command)
        return await box.run_tool(use, speech)

    platform = box.through(run)
    scripted: JsonObject = {"replies": list(replies)}
    call = Call(context_of(box.log.call), config, platform)
    session = text_session(call, Running(ACME, "a-key", options=scripted), Place())
    return session


async def said_until_the_end(session: Session, store: Store, call: str) -> list[str]:
    """What the agent said, once the call the app hung up has closed."""
    await asyncio.wait_for(session.over.wait(), 5)
    return [entry.data["text"] for entry in await store.whole_of(call) if entry.type == "turn.agent"]


@needs_the_database
async def test_a_tool_that_hung_up_is_not_answered_so_the_goodbye_said_with_it_is_the_last_word(
    box: Box, store: Store, call: str
) -> None:
    goodbye: list[Json] = ["Goodbye, Tom.", {"name": "finish", "arguments": {}, "call_id": "t1"}]
    monologue: list[Json] = ["Hello? The caller already hung up, so this call has ended."]
    session = commanding_through(box, FINISHING, CallHangup(), [goodbye, monologue])
    await session.start()
    await hear(session, "that is all, thanks, bye")
    assert await said_until_the_end(session, store, call) == ["Goodbye, Tom."]
    assert len(model_of(session).requests) == 1


@needs_the_database
async def test_a_tool_that_hung_up_in_silence_is_answered_once_so_the_goodbye_is_said(
    box: Box, store: Store, call: str
) -> None:
    finish: list[Json] = [{"name": "finish", "arguments": {}, "call_id": "t1"}]
    session = commanding_through(box, FINISHING, CallHangup(), [finish, ["Goodbye."]])
    await session.start()
    await hear(session, "that is all, thanks, bye")
    assert await said_until_the_end(session, store, call) == ["Goodbye."]
    assert len(model_of(session).requests) == 2


# The SDKs await a reply asked inside a tool (`await this.reply(…)`): it is asked of the model at once,
# its instruction in that request, so the tool goes on; held until the tool answered, the two waited
# on each other until the tool's timeout (2026-10-24).
@needs_the_database
async def test_a_reply_the_app_asks_for_while_its_tool_runs_is_asked_at_once_with_its_instruction(
    box: Box, store: Store, call: str
) -> None:
    hold: list[Json] = [{"name": "hold_line", "arguments": {}, "call_id": "t1"}]
    asked = AgentReply(instructions="Say only the word PINEAPPLE.")
    session = commanding_through(box, HOLDING, asked, [hold, ["PINEAPPLE"], ["After the tool."]])
    await session.start()
    await hear(session, "check it for me")
    await until(lambda: len(model_of(session).requests) >= 3)
    await settled()
    await session.end("caller_hung_up", "caller")
    asked_with = [str(getattr(item, "text_content", "")) for item in model_of(session).requests[1].items]
    assert "Say only the word PINEAPPLE." in asked_with
    said = [entry.data["text"] for entry in await store.whole_of(call) if entry.type == "turn.agent"]
    assert said[0] == "PINEAPPLE"


# A tutor's walk and an element's line are said by the app inside a quiet tool: that is the turn's
# answer, said once.
@needs_the_database
async def test_words_the_app_says_inside_a_quiet_tool_are_the_turns_answer_said_once(
    box: Box, store: Store, call: str
) -> None:
    point: list[Json] = [{"name": "point", "arguments": {"ref": "e12"}, "call_id": "t1"}]
    said_by_the_app = AgentSay(text="Here are our plans.")
    session = commanding_through(box, POINTING, said_by_the_app, [point, ["Here are our plans."]])
    await session.start()
    await hear(session, "where are the prices?")
    await settled()
    await session.end("caller_hung_up", "caller")
    said = [entry.data["text"] for entry in await store.whole_of(call) if entry.type == "turn.agent"]
    assert said == ["Here are our plans."]
    assert len(model_of(session).requests) == 1


# The interrupt's future waits for the speech running the tool: awaited, the line was marked held
# five seconds after the tool asked, livekit's timeout (2026-10-24).
@needs_the_database
async def test_a_hold_asked_from_a_tool_is_written_held_before_the_tool_answers(
    box: Box, store: Store, call: str
) -> None:
    hold: list[Json] = [{"name": "hold_line", "arguments": {}, "call_id": "t1"}]
    session = commanding_through(box, HOLDING, CallHold(), [hold, ["One moment."]])
    await session.start()
    began = time.monotonic()
    await hear(session, "can you check that for me?")
    await session.end("caller_hung_up", "caller")
    kinds_ = [entry.type for entry in await store.whole_of(call) if entry.type in ("call.line", "tool.result")]
    assert kinds_ == ["call.line", "tool.result"]
    assert time.monotonic() - began < 4.0


@needs_the_database
async def test_tools_chained_in_silence_are_announced_once_for_the_callers_turn(
    box: Box, store: Store, call: str
) -> None:
    session = a_session(
        box,
        LOOKING,
        [{"name": "look", "arguments": {"day": "lunes"}, "call_id": "t1"}],
        [{"name": "look", "arguments": {"day": "martes"}, "call_id": "t2"}],
        ["El lunes no, el martes hay hueco a las nueve."],
    )
    await session.start()
    await hear(session, "¿qué hay el lunes o el martes?")
    await session.end("caller_hung_up", "caller")
    agent = [entry.data["text"] for entry in await store.whole_of(call) if entry.type == "turn.agent"]
    assert agent == ["Un momento, miro la agenda.", "El lunes no, el martes hay hueco a las nueve."]


@needs_the_database
async def test_a_turn_that_spoke_before_calling_the_tool_is_not_announced_twice(
    box: Box, store: Store, call: str
) -> None:
    session = a_session(
        box,
        LOOKING,
        [
            "Voy a mirar la agenda.",
            {"name": "look", "arguments": {"day": "lunes"}, "call_id": "t1"},
        ],
        ["El lunes hay hueco a las nueve."],
    )
    await session.start()
    await hear(session, "¿qué hay el lunes?")
    await session.end("caller_hung_up", "caller")
    agent = [entry.data["text"] for entry in await store.whole_of(call) if entry.type == "turn.agent"]
    assert agent == ["Voy a mirar la agenda.", "El lunes hay hueco a las nueve."]


@needs_the_database
async def test_the_line_the_model_wrote_for_a_tool_is_said_as_it_runs_and_never_reaches_the_app(
    box: Box, store: Store, call: str
) -> None:
    session = a_session(
        box,
        BOOKING,
        [{"name": "cancel", "arguments": {"say": "Un segundo, la anulo."}, "call_id": "t1"}],
        ["Anulada."],
    )
    await session.start()
    await hear(session, "anule la reserva")
    await session.end("caller_hung_up", "caller")
    entries = await store.whole_of(call)
    agent = [entry.data["text"] for entry in entries if entry.type == "turn.agent"]
    assert agent == ["Un segundo, la anulo.", "Anulada."]
    called = next(entry for entry in entries if entry.type == "tool.call")
    assert called.data["arguments"] == {}


@needs_the_database
async def test_the_models_own_line_is_said_over_the_tools_announcement(box: Box, store: Store, call: str) -> None:
    session = a_session(
        box,
        LOOKING,
        [{"name": "look", "arguments": {"day": "lunes", "say": "Miro el lunes."}, "call_id": "t1"}],
        ["El lunes hay hueco a las nueve."],
    )
    await session.start()
    await hear(session, "¿qué hay el lunes?")
    await session.end("caller_hung_up", "caller")
    agent = [entry.data["text"] for entry in await store.whole_of(call) if entry.type == "turn.agent"]
    assert agent == ["Miro el lunes.", "El lunes hay hueco a las nueve."]


@needs_the_database
async def test_a_lookup_the_model_calls_is_said_with_the_line_it_wrote(box: Box, store: Store, call: str) -> None:
    reading = Declaration(slug="clinica-norte", bases=(Docs(base="faq"),))
    arguments: JsonObject = {"query": "horario", "say": "Lo busco."}
    session = a_session(
        box,
        reading,
        [{"name": "search", "arguments": arguments, "call_id": "t1"}],
        ["Abre a las nueve."],
    )
    await session.start()
    await hear(session, "¿a qué hora abren?")
    await session.end("caller_hung_up", "caller")
    agent = [entry.data["text"] for entry in await store.whole_of(call) if entry.type == "turn.agent"]
    assert agent == ["Lo busco.", "Abre a las nueve."]
    assert box.lookups[-1] == ("search", {"query": "horario"})


@needs_the_database
async def test_a_tool_that_failed_is_an_error_the_model_reads_and_no_read_back(
    box: Box, store: Store, call: str
) -> None:
    box.answers["book"] = ToolResult(call_id="t1", name="book", error="no hay mesas")
    session = a_session(
        box,
        BOOKING,
        [{"name": "book", "arguments": {"day": "lunes"}, "call_id": "t1"}],
        ["Lo siento"],
    )
    await session.start()
    await hear(session, "reserva el lunes")
    await session.end("caller_hung_up", "caller")
    output = output_of(session, "t1")
    assert (output.output, output.is_error) == ("no hay mesas", True)
    agent = [entry.data["text"] for entry in await store.whole_of(call) if entry.type == "turn.agent"]
    assert agent == ["Lo siento"]


@needs_the_database
async def test_a_tool_the_app_closed_is_refused_before_the_app_and_the_model_reads_why(
    box: Box, store: Store, call: str
) -> None:
    session = a_session(box, BOOKING, [{"name": "cancel", "call_id": "t9"}], ["No puedo cancelar"])
    await session.start()
    await apply(session, ToolsSet(tools=[WiredTool(name="book", description="d", parameters={"type": "object"})]))
    await hear(session, "cancelá")
    await session.end("caller_hung_up", "caller")
    assert box.used == []
    entries = await store.whole_of(call)
    assert next(entry for entry in entries if entry.type == "tools.changed").data == {"visible": ["book"]}
    refused = next(entry for entry in entries if entry.type == "error")
    assert (refused.data["code"], refused.data["message"]) == (
        "refused",
        "cancel is not available now",
    )
    assert output_of(session, "t9").output == "cancel is not available now"


@needs_the_database
async def test_a_tools_set_between_two_requests_leaves_the_providers_tools_byte_identical(
    box: Box,
) -> None:
    session = a_session(box, BOOKING, ["uno"], ["dos"])
    await session.start()
    await hear(session, "hola")
    await apply(session, ToolsSet(tools=[]))
    await hear(session, "hola otra vez")
    await session.end("caller_hung_up", "caller")
    first, second = model_of(session).requests
    assert first.tools == second.tools


@needs_the_database
async def test_a_state_set_during_a_tool_cites_the_tool_as_its_cause(box: Box, store: Store, call: str) -> None:
    session = a_session(box, BOOKING, [{"name": "book", "arguments": {"day": "lunes"}, "call_id": "t1"}], ["ok"])

    async def answering(_use: ToolUse, _speech: str | None) -> ToolResult:
        await apply(session, StateSet(state={"booked": True}))
        return ToolResult(call_id="t1", name="book", output="ok")

    session.call.platform = box.through(answering)
    await session.start()
    await hear(session, "reserva")
    await session.end("caller_hung_up", "caller")
    state = next(entry for entry in await store.whole_of(call) if entry.type == "state.changed")
    assert state.data["cause"] == {"kind": "tool", "tool": "book", "call_id": "t1"}


# ── tools ──


@needs_the_database
async def test_the_receipt_does_not_make_the_model_answer_itself(box: Box, store: Store, call: str) -> None:
    box.answers["book"] = ToolResult(call_id="t1", name="book", output={"table": "mesa 4"})
    session = a_session(
        box,
        BOOKING,
        ["Le reservo", {"name": "book", "arguments": {"day": "lunes"}, "call_id": "t1"}],
        ["¿Algo más?"],
    )
    await session.start()
    await hear(session, "reserva el lunes")
    await session.end("caller_hung_up", "caller")
    agent = [entry.data["text"] for entry in await store.whole_of(call) if entry.type == "turn.agent"]
    assert agent == [
        "Le reservo",
        "Reservado para el lunes, mesa 4 {{result.missing}}.",
        "¿Algo más?",
    ]
    assert len(model_of(session).requests) == 2


@needs_the_database
async def test_a_platform_that_refuses_is_a_tool_that_did_not_answer_and_the_call_goes_on(
    box: Box,
) -> None:
    async def refusing(_use: ToolUse, _speech: str | None) -> ToolResult:
        raise ServiceUnavailable("the app is not connected")

    session = a_session(box, BOOKING, [{"name": "book", "arguments": {}, "call_id": "t1"}], ["Probemos luego"])
    session.call.platform = box.through(refusing)
    await session.start()
    sentence = await hear(session, "reserva")
    await session.end("caller_hung_up", "caller")
    output = output_of(session, "t1")
    assert (output.output, output.is_error) == ("the app is not connected", True)
    assert sentence == "Probemos luego"


# The words the model said before its tools are heard whole before the app is asked: livekit's
# playout is waited for, and the speaker here says when it played.
@needs_the_database
async def test_the_tools_run_once_the_words_before_them_were_heard(box: Box) -> None:
    assert box.log.call is not None
    replies: list[list[Json]] = [
        ["Le reservo y le cancelo la otra", {"name": "book", "call_id": "t1"}, {"name": "cancel", "call_id": "t2"}],
        ["hecho"],
    ]
    stages = Pipeline(
        llm=Running(ACME, "k", options={"replies": replies}), stt=Running(ACME, "k"), tts=Running(ACME, "k")
    )
    session = voice_session(Call(context_of(box.log.call, Channel.phone), BOOKING, box), stages, Place())
    speaker = Speaker()
    session.live.output.audio = speaker
    await session.start()
    session.live.generate_reply(user_input="reservá y cancelá")
    await until(lambda: speaker.playing)
    await settled()
    assert box.used == [], "no tool runs while its words still play"
    speaker.played()
    await until(lambda: [use.name for use in box.used] == ["book", "cancel"])
    # The model's answer to the tools is heard to its end too, and the call can close.
    await until(lambda: speaker.playing)
    speaker.played()
    await session.close()
