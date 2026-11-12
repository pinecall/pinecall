"""One session for a spoken call and a written one: its opening, what livekit tells it, its recording, its end."""

import asyncio
import time
from collections.abc import AsyncIterator
from pathlib import Path

import av
from livekit.agents import (
    AgentStateChangedEvent,
    APIStatusError,
    CloseEvent,
    CloseReason,
    ConversationItemAddedEvent,
    UserInputTranscribedEvent,
    UserStateChangedEvent,
    llm,
    metrics,
)
from livekit.agents import ErrorEvent as ComponentFailed
from livekit.agents.beta.tools import EndCallTool
from livekit.agents.language import LanguageCode
from livekit.agents.llm.tool_context import ToolFlag
from livekit.agents.types import TimedString
from livekit.agents.voice import ModelSettings

import runtime
from runtime.agents.declaration import Declaration, Greeting, Hangup, MemoryPolicy
from runtime.calls.log.store import Store
from runtime.enums import Channel
from runtime.kit.text import JsonObject
from runtime.providers.stage import Pipeline, Running
from runtime.session.call import Call, ToolUse
from runtime.session.commands import apply
from runtime.session.hearing import keyterms
from runtime.session.hold import HoldMusic
from runtime.session.lookups import TEXT_LOOKUP_MS, VOICE_LOOKUP_MS
from runtime.session.session import TOOL_STEPS, Place, Session
from runtime.session.text import text_session
from runtime.session.tools import SAY_GOODBYE_FIRST
from runtime.session.voice import voice_session
from runtime.wire.commands import (
    AgentReply,
)
from runtime.wire.metrics import ModelUsage
from runtime.wire.parts import ToolResult
from tests.conftest import needs_the_database, until
from tests.fakes.acme import ACME
from tests.fakes.livekit import Microphone, Player, Server, Speaker, tone
from tests.fakes.livekit import Room as AnOfflineRoom
from tests.session.conftest import (
    CANCEL,
    NOBODY,
    Box,
    Through,
    a_block,
    a_room,
    a_session,
    context_of,
    hear,
    heard_live,
    kinds,
    model_of,
    settled,
    spoken_call,
)

# ── the opening ──


@needs_the_database
async def test_a_call_starts_with_call_started_then_the_knowledge_it_ships_with(
    box: Box, store: Store, call: str
) -> None:
    session = a_session(box, Declaration(slug="clinica-norte", knowledge="# Abrimos a las nueve"))
    await session.start()
    await session.end("caller_hung_up", "caller")
    entries = await store.whole_of(call)
    assert [entry.type for entry in entries][:2] == ["call.started", "prompt.changed"]
    assert entries[1].data["name"] == "knowledge"
    assert "Abrimos" not in str(entries[1].data)


@needs_the_database
async def test_a_call_opened_with_no_room_starts_as_a_written_one(box: Box, store: Store, call: str) -> None:
    session = a_session(box, Declaration(slug="clinica-norte"))
    await session.start()
    await session.end("caller_hung_up", "caller")
    entries = await store.whole_of(call)
    assert entries[0].data["medium"] == "text"


@needs_the_database
async def test_a_class_that_ships_no_file_writes_no_line_about_one(box: Box, store: Store, call: str) -> None:
    session = a_session(box, NOBODY)
    await session.start()
    await session.end("caller_hung_up", "caller")
    assert "prompt.changed" not in await kinds(store, call)


@needs_the_database
async def test_words_run_the_verbatim_verb_and_nothing_else(box: Box, store: Store, call: str) -> None:
    session = a_session(box, Declaration(slug="clinica-norte", greeting=Greeting(say="Buenas, clínica.")))
    await session.start()
    await settled()
    await session.end("caller_hung_up", "caller")
    agent = [entry.data["text"] for entry in await store.whole_of(call) if entry.type == "turn.agent"]
    assert agent == ["Buenas, clínica."]
    assert model_of(session).requests == []


@needs_the_database
async def test_an_instruction_runs_the_model_and_never_the_verbatim_verb(box: Box, store: Store, call: str) -> None:
    session = a_session(
        box,
        Declaration(slug="clinica-norte", greeting=Greeting(reply="Saluda")),
        ["Hola, ¿qué necesita?"],
    )
    await session.start()
    await settled()
    await session.end("caller_hung_up", "caller")
    assert len(model_of(session).requests) == 1
    agent = [entry.data["text"] for entry in await store.whole_of(call) if entry.type == "turn.agent"]
    assert agent == ["Hola, ¿qué necesita?"]


@needs_the_database
async def test_an_empty_instruction_has_the_model_open_on_its_prompt_alone(box: Box, store: Store, call: str) -> None:
    session = a_session(
        box,
        Declaration(slug="clinica-norte", greeting=Greeting(reply="")),
        ["Clínica Norte, ¿en qué le ayudo?"],
    )
    await session.start()
    await settled()
    await session.end("caller_hung_up", "caller")
    assert len(model_of(session).requests) == 1
    agent = [entry.data["text"] for entry in await store.whole_of(call) if entry.type == "turn.agent"]
    assert agent == ["Clínica Norte, ¿en qué le ayudo?"]


@needs_the_database
async def test_the_opening_is_said_before_the_greeting_and_logged_as_the_agents_turn(
    box: Box, store: Store, call: str
) -> None:
    session = a_session(box, Declaration(slug="clinica-norte", greeting=Greeting(say="Buenas")))
    await session.start(notice="Le habla un asistente automático en nombre de Clínica Norte.")
    await settled()
    await session.end("caller_hung_up", "caller")
    agent = [entry.data["text"] for entry in await store.whole_of(call) if entry.type == "turn.agent"]
    assert agent == ["Le habla un asistente automático en nombre de Clínica Norte.", "Buenas"]


@needs_the_database
async def test_a_call_a_run_opened_is_not_greeted_at_all(box: Box, store: Store, call: str) -> None:
    greeted = Declaration(slug="clinica-norte", greeting=Greeting(say="Buenas"))
    session = a_session(box, greeted, run="run_1")
    await session.start()
    await settled()
    await session.end("caller_hung_up", "caller")
    assert "turn.agent" not in await kinds(store, call)


# A visitor who resumed a conversation that had ended is not met as a stranger.
@needs_the_database
async def test_a_call_that_carries_another_on_opens_on_its_turns_and_greets_nobody(
    box: Box, store: Store, call: str
) -> None:
    carried = llm.ChatContext.empty()
    carried.add_message(role="user", content="Quiero una cita el lunes")
    carried.add_message(role="assistant", content="¿A qué hora le viene bien?")
    greeted = Declaration(slug="clinica-norte", greeting=Greeting(say="Buenas"))
    resumed = Call(context_of(call), greeted, box, None, carried)
    session = text_session(resumed, Running(ACME, "a-key", options={"replies": []}), Place())
    await session.start()
    await settled()
    history = session.agent.chat_ctx.items
    messages = [item.text_content for item in history if isinstance(item, llm.ChatMessage)]
    await session.end("caller_hung_up", "caller")
    assert messages[-2:] == ["Quiero una cita el lunes", "¿A qué hora le viene bien?"]
    assert "turn.agent" not in await kinds(store, call)


# ── what livekit tells the session ──


@needs_the_database
async def test_an_interim_is_an_ephemeral_transcript_and_starts_the_lookups(box: Box) -> None:
    seen = heard_live(box)
    session = a_session(box, Declaration(slug="clinica-norte", memory=MemoryPolicy()))
    await session.start()
    sentence = "quiero cambiar mi turno del lunes"
    session.live.emit(
        "user_input_transcribed",
        UserInputTranscribedEvent(transcript=sentence, is_final=False, language=LanguageCode("es")),
    )
    await settled()
    await session.end("caller_hung_up", "caller")
    heard = [entry for entry in seen if entry.type == "user.transcript"]
    assert (heard[0].data["final"], heard[0].ephemeral) == (False, True)
    assert box.lookups == [("recall", {"contact": "+59899123456", "query": sentence})]


@needs_the_database
async def test_a_turn_too_short_to_start_a_run_starts_none_before_the_turn_ends(box: Box) -> None:
    session = a_session(box, Declaration(slug="clinica-norte", memory=MemoryPolicy()))
    await session.start()
    session.live.emit("user_input_transcribed", UserInputTranscribedEvent(transcript="sí, eso", is_final=False))
    await settled()
    await session.end("caller_hung_up", "caller")
    assert box.lookups == []


@needs_the_database
async def test_a_voice_that_does_not_exist_ends_the_call_after_one_error_and_no_retry(
    box: Box, store: Store, call: str
) -> None:
    session = a_session(box, NOBODY)
    await session.start()
    refused = APIStatusError("voice not found", status_code=404)
    failed = ComponentFailed(error=_component_error(refused), source=model_of(session))
    session.live.emit("error", failed)
    session.live.emit("error", failed)
    await session.close()
    entries = await store.whole_of(call)
    errors = [entry.data["code"] for entry in entries if entry.type == "error"]
    assert errors == ["component_dead_end"]
    ended = next(entry for entry in entries if entry.type == "call.ended")
    assert (ended.data["reason"], ended.data["ended_by"]) == ("error", "platform")


@needs_the_database
async def test_a_vendor_having_a_bad_minute_is_written_and_the_call_goes_on(box: Box, store: Store, call: str) -> None:
    session = a_session(box, NOBODY)
    await session.start()
    busy = APIStatusError("overloaded", status_code=529)
    session.live.emit(
        "error",
        ComponentFailed(error=_component_error(busy, recoverable=True), source=model_of(session)),
    )
    await settled()
    await session.end("caller_hung_up", "caller")
    errors = [entry.data for entry in await store.whole_of(call) if entry.type == "error"]
    assert (errors[0]["code"], errors[0]["recoverable"]) == ("component_failed", True)
    ended = next(entry for entry in await store.whole_of(call) if entry.type == "call.ended")
    assert ended.data["reason"] == "caller_hung_up"


@needs_the_database
async def test_an_agent_turn_carries_its_report_whole_and_whether_it_was_cut_off(
    box: Box, store: Store, call: str
) -> None:
    session = a_session(box, NOBODY)
    await session.start()
    sentence = llm.ChatMessage(role="assistant", content=["Hasta"], interrupted=True, metrics={"llm_node_ttft": 0.3})
    session.live.emit("conversation_item_added", ConversationItemAddedEvent(item=sentence))
    await session.end("caller_hung_up", "caller")
    turn = next(entry for entry in await store.whole_of(call) if entry.type == "turn.agent")
    assert (turn.data["text"], turn.data["interrupted"]) == ("Hasta", True)
    assert turn.data["metrics"] == {"llm_node_ttft": 0.3}


# ── a spoken call's session ──


def test_the_declared_words_come_first_and_the_state_adds_the_names_it_holds() -> None:
    config = Declaration(slug="clinica-norte", hears=("Vidal",))
    state: JsonObject = {
        "patient": {"name": "Ana Pérez", "phone": "+59899123456"},
        "note": "x " * 30,
        "who": "Vidal",
    }
    assert keyterms(config, state) == ["Vidal", "Ana Pérez"]


# ── end_call ──


@needs_the_database
async def test_a_class_that_declares_no_hangup_gets_no_tool(box: Box) -> None:
    session = a_session(box, NOBODY)
    assert not any(isinstance(tool, EndCallTool) for tool in session.agent.tools)


@needs_the_database
async def test_the_tenants_words_and_the_goodbye_reach_livekits_own_end_call(box: Box) -> None:
    session = a_session(box, Declaration(slug="clinica-norte", hangup=Hangup(when="when they say bye")))
    (ending,) = [tool for tool in session.agent.tools if isinstance(tool, EndCallTool)]
    (end_call,) = ending.tools
    assert isinstance(end_call, llm.FunctionTool)
    described = end_call.info.description or ""
    assert "when they say bye" in described
    assert SAY_GOODBYE_FIRST in described
    # Hidden while the agent greets, or a model hangs up before the caller speaks.
    assert end_call.info.flags & ToolFlag.IGNORE_ON_ENTER


def _component_error(error: Exception, *, recoverable: bool = False) -> object:
    return llm.LLMError(timestamp=time.time(), label="acme", error=error, recoverable=recoverable)


# ── what the agent says, piece by piece ──


@needs_the_database
async def test_an_aligned_reply_is_logged_word_by_word_with_livekits_own_timings(box: Box) -> None:
    seen = heard_live(box)
    session = a_session(box, NOBODY)
    await session.start()
    words = [
        TimedString("Hola", start_time=0.0, end_time=0.3),
        TimedString(" Ana", start_time=0.3, end_time=0.6),
    ]
    passed = [piece async for piece in session.agent.transcription_node(_pieces(*words), ModelSettings())]
    await session.end("caller_hung_up", "caller")
    assert passed == words
    sentence = [entry.data for entry in seen if entry.type == "agent.transcript"]
    assert [(item["text"], item.get("start"), item.get("end")) for item in sentence] == [
        ("Hola", 0.0, 0.3),
        (" Ana", 0.3, 0.6),
    ]


@needs_the_database
async def test_a_voice_that_aligned_nothing_leaves_the_timings_off_the_entry(box: Box) -> None:
    seen = heard_live(box)
    session = a_session(box, NOBODY)
    await session.start()
    async for _ in session.agent.transcription_node(_pieces("Hola"), ModelSettings()):
        pass
    await session.end("caller_hung_up", "caller")
    (sentence,) = [entry.data for entry in seen if entry.type == "agent.transcript"]
    assert "start" not in sentence
    assert "end" not in sentence


# ── what the caller says ──


@needs_the_database
async def test_the_callers_words_and_states_land_in_the_order_they_were_heard(box: Box) -> None:
    seen = heard_live(box)
    session = a_session(box, NOBODY)
    await session.start()
    session.live.emit("user_state_changed", UserStateChangedEvent(old_state="listening", new_state="speaking"))
    session.live.emit("user_input_transcribed", UserInputTranscribedEvent(transcript="hola", is_final=False))
    session.live.emit("agent_state_changed", AgentStateChangedEvent(old_state="listening", new_state="thinking"))
    await session.end("caller_hung_up", "caller")
    order = [entry.type for entry in seen if entry.type in {"user.state", "user.transcript", "agent.state"}]
    assert order[-3:] == ["user.state", "user.transcript", "agent.state"]


# A realtime model's caller turn has no stop of its own: the session saw the caller go quiet.
@needs_the_database
async def test_the_caller_going_quiet_is_kept_for_the_turn_it_ends(box: Box) -> None:
    session = a_session(box, NOBODY)
    await session.start()
    quiet = UserStateChangedEvent(old_state="speaking", new_state="listening", created_at=104.0)
    session.live.emit("user_state_changed", quiet)
    session.live.emit("user_state_changed", UserStateChangedEvent(old_state="listening", new_state="away"))
    assert session.listener.went_quiet_at == 104.0
    await session.end("caller_hung_up", "caller")


# Ears with no interims (Whisper) give the final alone, before the end of the turn is weighed: it
# starts the run, and an interim before it keeps the run it started.
@needs_the_database
async def test_a_final_transcript_starts_the_lookups_once_a_turn(box: Box) -> None:
    session = a_session(box, Declaration(slug="clinica-norte", memory=MemoryPolicy()))
    await session.start()
    sentence = "quiero cambiar mi turno del lunes"
    session.live.emit("user_input_transcribed", UserInputTranscribedEvent(transcript=sentence, is_final=True))
    session.live.emit("user_input_transcribed", UserInputTranscribedEvent(transcript=f"{sentence} sí", is_final=True))
    await settled()
    await session.end("caller_hung_up", "caller")
    assert box.lookups == [("recall", {"contact": "+59899123456", "query": sentence})]


# PINECALL_VOICE_LOOKUP_BUDGET_MS and its written twin, when the operator sets them.
@needs_the_database
async def test_a_lookup_budget_the_operator_set_is_the_one_a_session_waits(box: Box) -> None:
    assert box.log.call is not None
    call = Call(context_of(box.log.call, Channel.phone), NOBODY, box)
    stages = Pipeline(llm=Running(ACME, "k"), stt=Running(ACME, "k"), tts=Running(ACME, "k"))
    assert voice_session(call, stages, Place()).lookups.budget_ms == VOICE_LOOKUP_MS
    assert voice_session(call, stages, Place(), lookup_budget_ms=600).lookups.budget_ms == 600
    assert text_session(call, Running(ACME, "k"), Place()).lookups.budget_ms == TEXT_LOOKUP_MS
    assert text_session(call, Running(ACME, "k"), Place(), lookup_budget_ms=900).lookups.budget_ms == 900


# PINECALL_MAX_TOOL_STEPS, when the operator sets it: how many rounds of tools one answer may chain.
@needs_the_database
async def test_the_tool_steps_a_session_allows_are_ten_or_the_ones_the_operator_set(box: Box) -> None:
    assert box.log.call is not None
    call = Call(context_of(box.log.call, Channel.phone), NOBODY, box)
    stages = Pipeline(llm=Running(ACME, "k"), stt=Running(ACME, "k"), tts=Running(ACME, "k"))
    assert voice_session(call, stages, Place()).live.options.max_tool_steps == TOOL_STEPS == 10
    assert voice_session(call, stages, Place(), tool_steps=3).live.options.max_tool_steps == 3
    assert text_session(call, Running(ACME, "k"), Place()).live.options.max_tool_steps == 10
    assert text_session(call, Running(ACME, "k"), Place(), tool_steps=4).live.options.max_tool_steps == 4


@needs_the_database
async def test_an_agent_reply_is_no_query_and_asks_nobody(box: Box) -> None:
    session = a_session(box, Declaration(slug="clinica-norte", memory=MemoryPolicy()), ["ok"])
    await session.start()
    await apply(session, AgentReply(instructions="Ofrecé el martes a las diez de la mañana"))
    await settled()
    await session.end("caller_hung_up", "caller")
    assert box.lookups == []


# ── a barge-in ──


# The tool is livekit's to await after a cut (it may have booked already), so the turn is over
# when the app answered; what is ours must be gone by then, but the call's writer.
@needs_the_database
async def test_a_caller_cutting_in_mid_sentence_leaves_no_task_of_ours_behind_the_turn(
    box: Box, store: Store, call: str
) -> None:
    # livekit waits five seconds for an interrupted speech before it cancels it itself (1.8.8).
    answered = asyncio.Event()
    # The suite's loop also runs the served gateway's loops: only tasks born in this test count.
    before = asyncio.all_tasks()
    speaker, player = Speaker(), Player()
    melody = HoldMusic(Path("hold.ogg"), AnOfflineRoom("call_1"), player, after_s=0.01)
    session = _a_slow_cancellation(box, answered, melody)
    await session.start()
    session.live.output.audio = speaker
    session.live.generate_reply(user_input="cancelá mi reserva")
    await until(lambda: speaker.playing)
    heard = UserInputTranscribedEvent(transcript="no espere quiero cambiarla", is_final=False)
    session.live.emit("user_input_transcribed", heard)
    await session.live.interrupt()
    answered.set()
    draining = session.call.writing.draining
    await until(lambda: [task for task in asyncio.all_tasks() - before if _ours(task)] == [draining], within_s=10)
    await until(lambda: all(handle.done() for handle in player.handles))
    assert (speaker.cut, melody.running, melody.pending) == (1, 0, None)
    await session.close()
    turn = next(entry for entry in await store.whole_of(call) if entry.type == "turn.agent")
    assert turn.data["interrupted"] is True


# ── the ears' words ──


def test_an_agent_that_declared_nothing_and_holds_nothing_asks_for_nothing() -> None:
    assert keyterms(NOBODY, {}) == []


# ── the recording ──


@needs_the_database
async def test_a_spoken_calls_recording_is_whole_before_the_seal_names_it(
    box: Box, tmp_path: Path, server: Server
) -> None:
    assert box.log.call is not None
    audio = tmp_path / "audio.ogg"
    channels_at_the_seal: list[int] = []

    async def seal(usage: list[ModelUsage], outcome: str) -> None:
        with av.open(str(audio)) as container:
            channels_at_the_seal.append(container.streams.audio[0].channels)
        await box.seal(usage, outcome)

    stages = Pipeline(llm=Running(ACME, "k"), stt=Running(ACME, "k"), tts=Running(ACME, "k"))
    recorded = Call(context_of(box.log.call, Channel.phone), NOBODY, Through(box, sealing=seal), audio)
    # A spoken call is recorded from its room: in production it always has one.
    session = voice_session(recorded, stages, Place(room=a_room(box, recorded, server)))
    session.live.input.audio = Microphone(tone(300, 0.2))
    session.live.output.audio = Speaker()
    await session.start()
    assert session.recorder is not None
    await session.close()
    assert channels_at_the_seal == [2]


@needs_the_database
async def test_a_spoken_call_says_who_ends_the_callers_turn_right_after_it_started(
    box: Box, server: Server, store: Store, call: str
) -> None:
    session = spoken_call(box, NOBODY, turn_model="smart-turn-v3", server=server)
    session.live.input.audio = Microphone(tone(300, 0.2))
    session.live.output.audio = Speaker()
    await session.start()
    await session.close()
    written = await kinds(store, call)
    assert written.index("turn.detection") == written.index("call.started") + 1
    said = next(entry.data for entry in await store.whole_of(call) if entry.type == "turn.detection")
    assert said == {"by": "smart-turn", "model": "smart-turn-v3", "min_silence_s": 0.7}


# ── the end ──


@needs_the_database
async def test_a_worker_the_platform_took_down_is_drained_and_never_an_error(box: Box, store: Store, call: str) -> None:
    session = a_session(box, NOBODY)
    await session.start()
    session.live.emit("close", CloseEvent(reason=CloseReason.JOB_SHUTDOWN))
    await session.close()
    ended = next(entry for entry in await store.whole_of(call) if entry.type == "call.ended")
    assert (ended.data["reason"], ended.data["ended_by"]) == ("drained", "platform")


@needs_the_database
async def test_letting_go_of_the_session_leaves_no_listener_behind(box: Box) -> None:
    seen = heard_live(box)
    session = a_session(box, NOBODY)
    await session.start()
    await session.end("caller_hung_up", "caller")
    before = len(seen)
    session.live.emit("user_state_changed", UserStateChangedEvent(old_state="listening", new_state="away"))
    model_of(session).emit("metrics_collected", a_block())
    await settled()
    assert len(seen) == before


@needs_the_database
async def test_end_call_is_in_the_log_like_any_other_tool_and_its_reason_comes_first(
    box: Box, store: Store, call: str
) -> None:
    ending = Declaration(slug="clinica-norte", hangup=Hangup(when="cuando se despida"))
    session = a_session(box, ending, ["Chau", {"name": "end_call", "call_id": "e1"}], ["nunca"])
    await session.start()
    await hear(session, "chau, gracias")
    await asyncio.sleep(0.2)
    await session.close()
    entries = await store.whole_of(call)
    tools = [(entry.type, entry.data["name"]) for entry in entries if entry.type in {"tool.call", "tool.result"}]
    assert tools == [("tool.call", "end_call"), ("tool.result", "end_call")]
    ended = next(entry for entry in entries if entry.type == "call.ended")
    assert (ended.data["reason"], ended.data["ended_by"]) == ("agent_hung_up", "agent")


@needs_the_database
async def test_nothing_is_generated_after_end_call(box: Box) -> None:
    ending = Declaration(slug="clinica-norte", hangup=Hangup())
    session = a_session(box, ending, ["Chau", {"name": "end_call", "call_id": "e1"}], ["nunca"])
    await session.start()
    await hear(session, "chau")
    await asyncio.sleep(0.2)
    await session.close()
    assert len(model_of(session).requests) == 1


# ── metrics ──


@needs_the_database
async def test_the_ticks_of_a_streaming_stt_ride_the_stream_and_one_measured_once_is_stored(
    box: Box,
) -> None:
    seen = heard_live(box)
    session = a_session(box, NOBODY)
    await session.start()
    model_of(session).emit("metrics_collected", _heard_block(streamed=True))
    model_of(session).emit("metrics_collected", _heard_block(streamed=False))
    await settled()
    await session.end("caller_hung_up", "caller")
    blocks = [(entry.data["streamed"], entry.ephemeral) for entry in seen if entry.type == "metrics.stt"]
    assert blocks == [(True, True), (False, False)]


@needs_the_database
async def test_the_turns_own_transcription_delay_is_what_a_reader_reads(box: Box, store: Store, call: str) -> None:
    session = a_session(box, NOBODY)
    await session.start()
    heard = llm.ChatMessage(role="user", content=["hola"], metrics={"transcription_delay": 0.12})
    session.live.emit("conversation_item_added", ConversationItemAddedEvent(item=heard))
    await session.end("caller_hung_up", "caller")
    turn = next(entry for entry in await store.whole_of(call) if entry.type == "turn.user")
    assert turn.data["metrics"] == {"transcription_delay": 0.12}


@needs_the_database
async def test_a_turn_that_generated_no_token_leaves_its_ttft_out(box: Box, store: Store, call: str) -> None:
    session = a_session(box, NOBODY)
    await session.start()
    sentence = llm.ChatMessage(role="assistant", content=[""], metrics={})
    session.live.emit("conversation_item_added", ConversationItemAddedEvent(item=sentence))
    await session.end("caller_hung_up", "caller")
    turn = next(entry for entry in await store.whole_of(call) if entry.type == "turn.agent")
    assert turn.data["metrics"] == {}


# ── helpers of these tests ──


def _a_slow_cancellation(box: Box, answered: asyncio.Event, melody: HoldMusic) -> Session:
    """A spoken call whose model announces a cancellation it runs on an app that waits."""
    assert box.log.call is not None

    async def waiting(use: ToolUse, speech: str | None) -> ToolResult:
        await answered.wait()
        return await box.run_tool(use, speech)

    platform = box.through(waiting)
    config = Declaration(slug="clinica-norte", tools=(CANCEL,), memory=MemoryPolicy())
    announced = "Le cancelo la reserva del lunes, deme un momento que la busco en el sistema"
    script: JsonObject = {"replies": [[announced, {"name": "cancel", "call_id": "t1"}], ["Listo"]]}
    stages = Pipeline(llm=Running(ACME, "k", options=script), stt=Running(ACME, "k"), tts=Running(ACME, "k"))
    return voice_session(Call(context_of(box.log.call, Channel.phone), config, platform), stages, Place(melody=melody))


# A task is ours when any coroutine it is awaiting was written in the package: livekit's task
# running one of our tools counts.
def _ours(task: asyncio.Task[object]) -> bool:
    package = str(Path(runtime.__file__).parent)
    step: object = task.get_coro()
    while step is not None:
        code = getattr(step, "cr_code", None) or getattr(step, "ag_code", None)
        if code is not None and str(code.co_filename).startswith(package):
            return True
        step = getattr(step, "cr_await", None) or getattr(step, "ag_await", None)
    return False


async def _pieces(*pieces: str) -> AsyncIterator[str]:
    for piece in pieces:
        yield piece


def _heard_block(*, streamed: bool) -> metrics.STTMetrics:
    return metrics.STTMetrics(
        label="acme", request_id="r1", timestamp=time.time(), duration=0.0,
        audio_duration=1.0, streamed=streamed,
    )  # fmt: skip
