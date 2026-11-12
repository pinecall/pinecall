"""Tests for a session opened for a spoken call: the pipeline, the turn options, the keyterms."""

from typing import override

import pytest
from livekit.agents.voice import AgentSession
from livekit.agents.voice.agent_session import DEFAULT_TTS_TEXT_TRANSFORMS

from runtime.agents.declaration import Declaration, Turn
from runtime.calls.log.store import Store
from runtime.kit.text import JsonObject
from runtime.providers.service.stages import LLMWithRequest
from runtime.session.commands import apply
from runtime.session.hearing import FALSE_INTERRUPTION_TIMEOUT_S, MIN_WORDS, keyterms
from runtime.session.session import Place, Session
from runtime.session.stages import is_spoken
from runtime.session.voice import SILENCE_S
from runtime.wire import events as wire
from runtime.wire.commands import CallHold, CallUnhold, ReleaseVerb, StateSet, TakeoverVerb
from tests.conftest import needs_the_database
from tests.fakes import talker
from tests.fakes.acme import ACME, AcmeLLM, AcmeTTS
from tests.fakes.livekit import Microphone, Speaker
from tests.fakes.talker import SayingRealtime, TalkerRealtime
from tests.session.conftest import (
    NOBODY,
    Box,
    a_session,
    kinds,
    settled,
    spoken_call,
    supervised,
)


@needs_the_database
async def test_the_caller_is_pinned_before_livekit_links_a_seat_and_a_written_call_hears_none(box: Box) -> None:
    session = a_session(box, NOBODY, place_of=lambda _call: Place(participant="visitor_1"))
    options = session.room_options()
    assert options.participant_identity == "visitor_1"
    assert (options.audio_input, options.audio_output) == (False, False)
    # Only a widget's visitor is waited for; any other caller leaving closes the session.
    assert options.close_on_disconnect is True


async def test_a_call_on_a_realtime_model_is_spoken_without_ears_and_a_written_one_is_not() -> None:
    voice = AcmeTTS(speech_key="k")
    assert is_spoken(AgentSession(llm=TalkerRealtime(api_key="k"), tts=voice), (voice,))
    assert not is_spoken(AgentSession(llm=AcmeLLM(api_key="k")), ())


@needs_the_database
@pytest.mark.parametrize("says", [True, False])
async def test_a_realtime_model_that_says_given_words_is_the_calls_only_voice(box: Box, says: bool) -> None:
    session = spoken_call(box, NOBODY, realtime=talker.install_saying() if says else talker.install())
    assert isinstance(session.live.llm, SayingRealtime if says else TalkerRealtime)  # pyright: ignore[reportUnknownMemberType]
    # livekit says given words through a TTS whenever the session has one.
    assert (session.live.tts is None) is says  # pyright: ignore[reportUnknownMemberType]
    assert [type(stage).__name__ for stage in session.built] == ([] if says else ["AcmeTTS"])


@needs_the_database
async def test_a_spoken_call_is_built_with_the_ears_the_voice_and_the_model_it_asked_for(
    box: Box,
) -> None:
    session = spoken_call(box, Declaration(slug="clinica-norte"))
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


# 2026-11-06: on Scribe the agent spoke over a caller who paused between sentences: the detector closed the
# turn on the first silence, and `endpointing_ms`, which would have made it wait, was refused as untaken.
@needs_the_database
async def test_the_agents_endpointing_is_the_least_silence_the_detector_waits_on_ears_that_leave_the_turn_open(
    box: Box,
) -> None:
    patient = Declaration(slug="clinica-norte", turn=Turn(endpointing_ms=800))
    local = spoken_call(box, patient)
    endpointing = local.live.options.turn_handling.get("endpointing") or {}
    assert (endpointing.get("min_delay"), endpointing.get("max_delay")) == (0.8, 3.0)
    assert local.turn == wire.TurnDetection(by="livekit", model="v1-mini", min_silence_s=0.8)
    # Ears that end the turn take the silence as their own timeout, and livekit's half second stays here.
    deciding = spoken_call(box, patient, ends_the_turn=True)
    assert (deciding.live.options.turn_handling.get("endpointing") or {}).get("min_delay") == 0.5
    assert deciding.turn == wire.TurnDetection(by="stt", model=ACME)
    # 2026-11-07: an agent that sets none waits the platform's 0.7 s, under either detector: livekit's
    # 0.3 s on Smart Turn and 0.5 s on its own cut a caller's sentence at its pauses.
    unset = spoken_call(box, NOBODY, turn_model="smart-turn-v3")
    assert (unset.live.options.turn_handling.get("endpointing") or {}).get("min_delay") == SILENCE_S == 0.7
    assert unset.turn == wire.TurnDetection(by="smart-turn", model="smart-turn-v3", min_silence_s=0.7)
    livekits = spoken_call(box, NOBODY)
    assert (livekits.live.options.turn_handling.get("endpointing") or {}).get("min_delay") == 0.7


@needs_the_database
async def test_what_it_takes_to_cut_the_agent_off_is_the_agents_own_else_two_words(
    box: Box,
) -> None:
    declared = spoken_call(box, Declaration(slug="clinica-norte", turn=Turn(min_interruption_words=4)))
    inherited = spoken_call(box, NOBODY)
    assert declared.live.options.interruption.get("min_words") == 4
    assert inherited.live.options.interruption.get("min_words") == MIN_WORDS == 2


# 2026-11-06: a caller finishing a phone number the ears had already closed stopped the reply being
# written, and with no resume it was never said: the agent sat silent until the caller spoke again.
@needs_the_database
async def test_a_sound_that_brings_no_words_within_a_second_is_false_and_the_reply_goes_on(box: Box) -> None:
    interruption = spoken_call(box, NOBODY).live.options.interruption
    assert interruption.get("resume_false_interruption") is True
    assert interruption.get("false_interruption_timeout") == FALSE_INTERRUPTION_TIMEOUT_S == 1.0


@needs_the_database
async def test_how_long_the_caller_must_speak_over_the_agent_is_the_agents_else_livekits(
    box: Box,
) -> None:
    declared = spoken_call(box, Declaration(slug="clinica-norte", turn=Turn(min_interruption_ms=900)))
    inherited = spoken_call(box, NOBODY)
    assert declared.live.options.interruption.get("min_duration") == 0.9
    assert inherited.live.options.interruption.get("min_duration") == 0.5, "livekit's own"


@needs_the_database
async def test_the_tenants_own_pronunciations_are_said_after_livekits_filters(box: Box) -> None:
    session = spoken_call(box, Declaration(slug="clinica-norte", says={"GSA": "ge ese a"}))
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
    session = spoken_call(box, Declaration(slug="clinica-norte", hears=("Vidal",)), keyterms=True)
    session.call.writing.open()
    await apply(session, StateSet(state={"patient": {"name": "Ana Pérez"}}))
    await session.call.writing.close(5)
    assert session.live.keyterms == ["Vidal", "Ana Pérez"]


@needs_the_database
async def test_ears_with_no_keyterms_door_are_never_told_anything(box: Box) -> None:
    session = spoken_call(box, Declaration(slug="clinica-norte", hears=("Vidal",)))
    session.call.writing.open()
    await apply(session, StateSet(state={"patient": {"name": "Ana Pérez"}}))
    await session.call.writing.close(5)
    assert session.live.keyterms == []
    assert session.live.options.stt_context_options.get("keyterms") == []


@needs_the_database
async def test_the_words_the_agent_declared_it_hears_reach_the_ears_that_take_them(
    box: Box,
) -> None:
    session = spoken_call(box, Declaration(slug="clinica-norte", hears=("Vidal", "GSA")), keyterms=True)
    assert session.live.options.stt_context_options.get("keyterms") == ["Vidal", "GSA"]
    unsaid = spoken_call(box, NOBODY, keyterms=True)
    assert unsaid.live.options.stt_context_options.get("keyterms") == []


@needs_the_database
async def test_a_spoken_call_asks_the_voice_to_align_the_transcript_it_speaks(box: Box) -> None:
    assert spoken_call(box, NOBODY).live.options.use_tts_aligned_transcript is True


class _Ears(Microphone):
    """A leg that says nothing, and notes when the agent is given it."""

    def __init__(self, switched: list[str]) -> None:
        super().__init__([])
        self.switched = switched

    @override
    def on_attached(self) -> None:
        self.switched.append("ears")


class _Voice(Speaker):
    """An ear that notes when the agent is given its voice."""

    def __init__(self, switched: list[str]) -> None:
        super().__init__()
        self.switched = switched

    @override
    def on_attached(self) -> None:
        self.switched.append("voice")


def plugged(session: Session) -> list[str]:
    """Ears and a voice for a muted agent; the list says, in order, which it is given back."""
    switched: list[str] = []
    session.live.input.audio = _Ears(switched)
    session.live.output.audio = _Voice(switched)
    assert switched == [], "the agent is muted when they are plugged"
    return switched


@needs_the_database
async def test_taking_the_call_off_hold_gives_the_agent_its_ears_before_its_voice(box: Box) -> None:
    session = a_session(box, NOBODY)
    await session.start()
    await apply(session, CallHold())
    switched = plugged(session)
    await apply(session, CallUnhold())
    await session.end("caller_hung_up", "caller")
    assert switched == ["ears", "voice"]


@needs_the_database
async def test_a_release_gives_the_ears_back_first_and_then_the_voice(box: Box, store: Store, call: str) -> None:
    session = a_session(box, NOBODY, ["¿Seguimos?"])
    await session.start()
    await apply(session, supervised(TakeoverVerb()))
    switched = plugged(session)
    await apply(session, supervised(ReleaseVerb()))
    await settled()
    await session.end("caller_hung_up", "caller")
    assert switched[:2] == ["ears", "voice"]
    assert "supervisor.released" in await kinds(store, call)
