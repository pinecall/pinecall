"""Tests for a session opened for a spoken call: the pipeline, the turn options, the keyterms."""

import pytest
from livekit.agents import llm
from livekit.agents.types import NotGiven
from livekit.agents.voice import AgentSession
from livekit.agents.voice.agent_session import DEFAULT_TTS_TEXT_TRANSFORMS
from livekit.agents.voice.room_io import RoomOptions

import pinecall_runtime.session.session as session_module
import pinecall_runtime.session.text as text
import pinecall_runtime.session.voice as voice_module
from pinecall_runtime.agents.declaration import AgentConfig, Turn
from pinecall_runtime.calls.store import Store
from pinecall_runtime.kit.text import JsonObject
from pinecall_runtime.providers.service.plugins import Running
from pinecall_runtime.providers.service.stages import LLMWithRequest
from pinecall_runtime.session.hearing import MIN_WORDS, keyterms
from pinecall_runtime.session.session import is_spoken
from pinecall_runtime.wire.commands import CallHold, CallUnhold, ReleaseVerb, StateSet, TakeoverVerb
from tests.conftest import needs_the_database
from tests.fakes.acme import AcmeLLM, AcmeTTS
from tests.providers.test_realtime import Talks
from tests.session.conftest import (
    Box,
    a_session,
    kinds,
)
from tests.session.test_session import NOBODY, settled, spoken_call, supervised


@needs_the_database
async def test_the_caller_is_pinned_before_livekit_links_a_seat_and_a_written_call_hears_none(
    box: Box, monkeypatch: pytest.MonkeyPatch
) -> None:
    given: list[RoomOptions] = []

    class Recorded(RoomOptions):
        def __init__(
            self,
            *,
            participant_identity: str | NotGiven,
            audio_input: bool | NotGiven,
            audio_output: bool | NotGiven,
            close_on_disconnect: bool,
        ) -> None:
            super().__init__(
                participant_identity=participant_identity,
                audio_input=audio_input,
                audio_output=audio_output,
                close_on_disconnect=close_on_disconnect,
            )
            given.append(self)

    monkeypatch.setattr(session_module, "RoomOptions", Recorded)
    session = a_session(box, NOBODY)
    await session.start(seat="visitor_1")
    await text.end_text(session, "caller_hung_up", "caller")
    (options,) = given
    assert options.participant_identity == "visitor_1"
    assert (options.audio_input, options.audio_output) == (False, False)
    # Only a widget's visitor is waited for; any other caller leaving closes the session.
    assert options.close_on_disconnect is True


def test_a_call_on_a_realtime_model_is_spoken_without_ears_and_a_written_one_is_not() -> None:
    voice = AcmeTTS(speech_key="k")
    assert is_spoken(AgentSession(llm=Talks(api_key="k"), tts=voice), (voice,))
    assert not is_spoken(AgentSession(llm=AcmeLLM(api_key="k")), ())


@needs_the_database
@pytest.mark.parametrize("says", [True, False])
async def test_a_realtime_model_that_says_given_words_is_the_calls_only_voice(
    box: Box, monkeypatch: pytest.MonkeyPatch, says: bool
) -> None:
    model = Talks(api_key="k")
    model.capabilities.supports_say = says

    def built(_stage: Running) -> llm.RealtimeModel:
        return model

    monkeypatch.setattr(voice_module, "build_realtime", built)
    session = spoken_call(box, NOBODY)
    assert session.live.llm is model  # pyright: ignore[reportUnknownMemberType]
    # livekit says given words through a TTS whenever the session has one.
    assert (session.live.tts is None) is says  # pyright: ignore[reportUnknownMemberType]
    assert [type(stage).__name__ for stage in session.built] == ([] if says else ["AcmeTTS"])


@needs_the_database
async def test_a_spoken_call_is_built_with_the_ears_the_voice_and_the_model_it_asked_for(
    box: Box,
) -> None:
    session = spoken_call(box, AgentConfig(slug="clinica-norte"))
    model, ears, voice = session.built
    assert isinstance(model, LLMWithRequest)
    assert [type(stage).__name__ for stage in (model.built, ears, voice)] == ["AcmeLLM", "AcmeSTT", "AcmeTTS"]


@needs_the_database
async def test_ears_that_end_the_turn_decide_it_and_others_get_the_local_detector(box: Box) -> None:
    deciding = spoken_call(box, NOBODY, ends_the_turn=True)
    local = spoken_call(box, NOBODY)
    assert deciding.live.options.turn_handling.get("turn_detection") == "stt"
    assert type(local.live.options.turn_handling.get("turn_detection")).__name__ == "TurnDetector"


@needs_the_database
async def test_the_row_may_read_the_turn_with_smart_turn_whose_weights_load_once(box: Box) -> None:
    first = spoken_call(box, NOBODY, turn_model="smart-turn-v3")
    detector = first.live.options.turn_handling.get("turn_detection")
    assert type(detector).__name__ == "SmartTurnDetector"
    again = spoken_call(box, NOBODY, turn_model="smart-turn-v3")
    assert again.live.options.turn_handling.get("turn_detection") is detector


@needs_the_database
async def test_what_it_takes_to_cut_the_agent_off_is_the_agents_own_else_two_words(
    box: Box,
) -> None:
    declared = spoken_call(box, AgentConfig(slug="clinica-norte", turn=Turn(min_interruption_words=4)))
    inherited = spoken_call(box, NOBODY)
    assert declared.live.options.interruption.get("min_words") == 4
    assert inherited.live.options.interruption.get("min_words") == MIN_WORDS == 2


@needs_the_database
async def test_how_long_the_caller_must_speak_over_the_agent_is_the_agents_else_livekits(
    box: Box,
) -> None:
    declared = spoken_call(box, AgentConfig(slug="clinica-norte", turn=Turn(min_interruption_ms=900)))
    inherited = spoken_call(box, NOBODY)
    assert declared.live.options.interruption.get("min_duration") == 0.9
    assert inherited.live.options.interruption.get("min_duration") == 0.5, "livekit's own"


@needs_the_database
async def test_the_tenants_own_pronunciations_are_said_after_livekits_filters(box: Box) -> None:
    session = spoken_call(box, AgentConfig(slug="clinica-norte", says={"GSA": "ge ese a"}))
    transforms = list(session.live.options.tts_text_transforms or [])
    assert transforms[: len(DEFAULT_TTS_TEXT_TRANSFORMS)] == list(DEFAULT_TTS_TEXT_TRANSFORMS)
    assert len(transforms) == len(DEFAULT_TTS_TEXT_TRANSFORMS) + 1


def test_the_keyterms_stop_where_the_vendors_do() -> None:
    state: JsonObject = {f"n{index}": f"Nombre {index}" for index in range(80)}
    assert len(keyterms(NOBODY, state)) == 50


@needs_the_database
async def test_the_vad_is_livekits_own_local_one_built_when_none_is_given(box: Box) -> None:
    session = spoken_call(box, NOBODY)
    assert session.live.vad is not None
    assert type(session.live.vad).__module__.startswith("livekit.agents.inference")


@needs_the_database
async def test_a_written_call_hears_nothing_speaks_nothing_and_takes_its_turns_by_hand(
    box: Box,
) -> None:
    session = a_session(box, NOBODY)
    (model,) = session.built
    assert isinstance(model, LLMWithRequest) and type(model.built).__name__ == "AcmeLLM"
    assert session.live.options.turn_handling.get("turn_detection") == "manual"


@needs_the_database
async def test_the_ears_are_told_the_names_the_state_is_holding_the_moment_it_moves(
    box: Box,
) -> None:
    session = spoken_call(box, AgentConfig(slug="clinica-norte", hears=("Vidal",)), keyterms=True)
    session.call.writing.open()
    await session.apply(StateSet(state={"patient": {"name": "Ana Pérez"}}))
    await session.call.writing.close(5)
    assert session.live.keyterms == ["Vidal", "Ana Pérez"]


@needs_the_database
async def test_ears_with_no_keyterms_door_are_never_told_anything(box: Box) -> None:
    session = spoken_call(box, AgentConfig(slug="clinica-norte", hears=("Vidal",)))
    session.call.writing.open()
    await session.apply(StateSet(state={"patient": {"name": "Ana Pérez"}}))
    await session.call.writing.close(5)
    assert session.live.keyterms == []
    assert session.live.options.stt_context_options.get("keyterms") == []


@needs_the_database
async def test_the_words_the_agent_declared_it_hears_reach_the_ears_that_take_them(
    box: Box,
) -> None:
    session = spoken_call(box, AgentConfig(slug="clinica-norte", hears=("Vidal", "GSA")), keyterms=True)
    assert session.live.options.stt_context_options.get("keyterms") == ["Vidal", "GSA"]
    unsaid = spoken_call(box, NOBODY, keyterms=True)
    assert unsaid.live.options.stt_context_options.get("keyterms") == []


@needs_the_database
async def test_a_spoken_call_asks_the_voice_to_align_the_transcript_it_speaks(box: Box) -> None:
    assert spoken_call(box, NOBODY).live.options.use_tts_aligned_transcript is True


@needs_the_database
async def test_taking_the_call_off_hold_gives_the_agent_its_ears_before_its_voice(
    box: Box, monkeypatch: pytest.MonkeyPatch
) -> None:
    session = a_session(box, NOBODY)
    await session.start()
    await session.apply(CallHold())
    switched: list[tuple[str, bool]] = []

    def ears(on: object) -> None:
        switched.append(("ears", on is True))

    def voice(on: object) -> None:
        switched.append(("voice", on is True))

    monkeypatch.setattr(session.live.input, "set_audio_enabled", ears)
    monkeypatch.setattr(session.live.output, "set_audio_enabled", voice)
    await session.apply(CallUnhold())
    await text.end_text(session, "caller_hung_up", "caller")
    assert switched == [("ears", True), ("voice", True)]


@needs_the_database
async def test_a_release_gives_the_ears_back_first_and_then_the_voice(
    box: Box, store: Store, call: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    session = a_session(box, NOBODY, ["¿Seguimos?"])
    await session.start()
    await session.apply(supervised(TakeoverVerb()))
    switched: list[str] = []

    def ears(_on: object) -> None:
        switched.append("ears")

    def voice(_on: object) -> None:
        switched.append("voice")

    monkeypatch.setattr(session.live.input, "set_audio_enabled", ears)
    monkeypatch.setattr(session.live.output, "set_audio_enabled", voice)
    await session.apply(supervised(ReleaseVerb()))
    await settled()
    await text.end_text(session, "caller_hung_up", "caller")
    assert switched[:2] == ["ears", "voice"]
    assert "supervisor.released" in await kinds(store, call)
