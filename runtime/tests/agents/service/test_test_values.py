"""A test room's own voice and models lie over the agent for its call alone, its class's as the org's."""

import pytest

from runtime.agents.declaration import Declaration
from runtime.agents.service import settings
from runtime.agents.service.resolution import lay_test_values, resolve
from runtime.agents.service.setting_names import TEST_FIELDS
from runtime.agents.settings import AgentSettings, Lexicon, read_settings
from runtime.enums import Env, Stage
from runtime.exceptions import Forbidden, ValidationError
from runtime.providers.stage import Model, Voice
from tests.fakes import acme, talker
from tests.fakes.acme import ACME

DEFAULTS: dict[Stage, str] = {Stage.llm: ACME, Stage.stt: ACME, Stage.tts: ACME}


def _tried(running: Declaration, **asked: object) -> Declaration:
    return lay_test_values(running, read_settings(asked), defaults=DEFAULTS)


def test_the_values_a_room_asked_for_win_knob_by_knob_and_the_rest_stay() -> None:
    running = Declaration(
        slug="kala", llm=Model(ACME, "acme-1", temperature=0.4), voice=Voice(ACME, voice_id="ana"), language="es"
    )
    tried = _tried(running, voice="lucia", temperature=0.9)
    assert tried.voice == Voice(ACME, voice_id="lucia")
    assert tried.llm == Model(ACME, "acme-1", temperature=0.9)
    assert tried.language == "es"


def test_a_rooms_model_runs_its_call_whatever_the_class_declares() -> None:
    """Four models asked for were four calls on the class's one until 2026-11-24: the class won over the room."""
    declared = Declaration(slug="kala", llm=Model(ACME, "acme-1"), fixed=frozenset({"llm"}))
    running = resolve(declared, AgentSettings(llm=f"{ACME}/the-orgs"), Lexicon(), defaults=DEFAULTS)
    assert running.llm == Model(ACME, "acme-1")
    assert _tried(running, llm=f"{ACME}/acme-2").llm == Model(ACME, "acme-2")


def test_a_temperature_alone_keeps_the_model_the_class_declares() -> None:
    running = Declaration(slug="kala", llm=Model(ACME, "acme-1", options={"seed": 7}), fixed=frozenset({"llm"}))
    assert _tried(running, temperature=0.2).llm == Model(ACME, "acme-1", temperature=0.2, options={"seed": 7})


def test_a_model_on_another_vendor_leaves_the_first_ones_plugin_and_options_behind() -> None:
    other = acme.install("acme-two")
    running = Declaration(
        slug="kala",
        llm=Model(ACME, "acme-1", temperature=0.3, builds="OtherLLM", options={"seed": 7}),
        stt=Model(ACME, "acme-ears", options={"keyterms": ["kala"]}, end_of_turn="livekit"),
    )
    tried = _tried(running, llm=f"{other}/big", stt=other)
    assert tried.llm == Model(other, "big", temperature=0.3)
    assert tried.stt == Model(other, "", end_of_turn="livekit")


def test_a_voice_on_another_vendor_leaves_the_agents_voice_behind_unless_the_room_names_one() -> None:
    other = acme.install("acme-two")
    running = Declaration(slug="kala", voice=Voice(ACME, model="acme-voice", voice_id="ana", options={"speed": 1.1}))
    assert _tried(running, tts=other).voice == Voice(other)
    assert _tried(running, tts=other, voice="lucia").voice == Voice(other, voice_id="lucia")
    assert _tried(running, tts_model="acme-voice-2").voice == Voice(
        ACME, model="acme-voice-2", voice_id="ana", options={"speed": 1.1}
    )


def test_an_agent_with_nothing_named_takes_the_rooms_values_on_the_boxs_vendors() -> None:
    tried = _tried(Declaration(slug="kala"), temperature=0.5, end_of_turn="livekit", voice="lucia")
    assert tried.llm == Model(ACME, "", temperature=0.5)
    assert tried.stt == Model(ACME, "", end_of_turn="livekit")
    assert tried.voice == Voice(ACME, voice_id="lucia")


# A value for every field a room may set: one added to the table and not laid here would be asked for
# and run nowhere, in silence, as the class's fields were.
A_VALUE: dict[str, object] = {
    "llm": f"{ACME}/acme-2",
    "temperature": 0.9,
    "stt": f"{ACME}/acme-ears-2",
    "end_of_turn": "livekit",
    "tts": f"{ACME}/acme-voice-2",
    "tts_model": "acme-voice-3",
    "voice": "lucia",
    "language": "fr",
    "smart_interruptions": False,
    "realtime": f"{talker.TALKER}/voice-3",
}


def test_every_field_a_room_may_set_changes_its_call_over_a_class_that_fixes_it() -> None:
    talker.install()
    assert set(A_VALUE) == TEST_FIELDS
    running = Declaration(
        slug="kala",
        llm=Model(ACME, "acme-1", temperature=0.1),
        stt=Model(ACME, "acme-ears", end_of_turn="stt"),
        voice=Voice(ACME, model="acme-voice", voice_id="ana"),
        language="es",
        fixed=frozenset({"llm", "stt", "voice", "language", "smart_interruptions"}),
    )
    for name, value in A_VALUE.items():
        assert _tried(running, **{name: value}) != running, name


# 2026-11-25: a comparison took the pipeline's models in one command and a realtime model in two more,
# the agent set on it and run apart.
def test_a_rooms_realtime_model_runs_its_call_and_a_model_to_think_with_takes_it_off_the_agents() -> None:
    vendor = talker.install()
    running = Declaration(slug="kala", llm=Model(ACME, "acme-1"))
    assert _tried(running, realtime=f"{vendor}/voice-3").realtime == Model(vendor, "voice-3")
    assert _tried(running, realtime=f"{vendor}/voice-3").llm == Model(ACME, "acme-1")
    talks = Declaration(slug="kala", llm=Model(ACME, "acme-1"), realtime=Model(vendor, "voice-1"))
    assert _tried(talks, voice="lucia").realtime == Model(vendor, "voice-1")
    assert _tried(talks, llm=f"{ACME}/acme-2").realtime is None
    assert _tried(talks, realtime=f"{vendor}/voice-3").realtime == Model(vendor, "voice-3")
    with pytest.raises(ValidationError, match="no model that hears and speaks itself"):
        _tried(running, realtime=f"{ACME}/acme-1")


def test_no_values_leave_the_agent_as_it_runs() -> None:
    running = Declaration(slug="kala", llm=Model(ACME, "acme-1"), voice=Voice(ACME, voice_id="ana"))
    assert _tried(running) == running


def test_the_sandbox_takes_a_voice_and_the_models_and_hands_back_what_it_checked() -> None:
    asked = {"tts": "acme", "voice": "lucia", "stt": "acme/nova", "llm": "acme/acme-2"}
    assert settings.check_test_values(asked, env=Env.sandbox) == asked


def test_production_refuses_them_and_says_whose_they_are() -> None:
    with pytest.raises(Forbidden, match="sandbox"):
        settings.check_test_values({"voice": "lucia"}, env=Env.production)


def test_a_room_changes_the_voice_and_the_models_and_nothing_else() -> None:
    with pytest.raises(ValidationError, match="record"):
        settings.check_test_values({"voice": "lucia", "record": False}, env=Env.sandbox)


def test_a_value_the_settings_would_refuse_is_refused_here_too() -> None:
    with pytest.raises(ValidationError):
        settings.check_test_values({"temperature": -1}, env=Env.sandbox)


def test_a_room_may_say_who_ends_the_callers_turn() -> None:
    asked = {"stt": "acme/nova", "end_of_turn": "livekit"}
    assert settings.check_test_values(asked, env=Env.sandbox) == asked


def test_a_room_may_run_its_call_with_the_model_that_judges_interruptions_or_without() -> None:
    """The same caller stopped by the model's word or by the ears' words: true or false, nothing else."""
    asked = {"smart_interruptions": False}
    assert settings.check_test_values(asked, env=Env.sandbox) == asked
    with pytest.raises(ValidationError, match="true or false"):
        settings.check_test_values({"smart_interruptions": 0}, env=Env.sandbox)
