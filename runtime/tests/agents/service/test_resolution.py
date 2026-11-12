"""The settings' realtime model is laid over the declaration beside its llm: named `vendor/model` or a
vendor alone, with its options, and never in the llm's place; a class's own wins over it."""

from collections.abc import Callable

import pytest

from runtime.agents.declaration import Declaration, Idle, Voicemail, check_idle, check_silence, check_voicemail
from runtime.agents.service.declaration import declare
from runtime.agents.service.resolution import resolve
from runtime.agents.service.settings import parse_settings
from runtime.agents.settings import AgentSettings, Lexicon
from runtime.enums import Stage
from runtime.exceptions import ValidationError
from runtime.providers.stage import Model
from runtime.wire.declaration import AgentConfig as Declared
from tests.fakes import talker
from tests.fakes.acme import ACME

DEFAULTS: dict[Stage, str] = {Stage.llm: ACME, Stage.stt: ACME, Stage.tts: ACME}
DECLARED = Declaration(slug="kala", llm=Model(ACME, "acme-1"), fixed=frozenset({"llm"}))


@pytest.fixture
def vendor() -> str:
    """The talker vendor, installed as a plugin."""
    return talker.install()


def _tuned(settings: AgentSettings, declared: Declaration = DECLARED) -> Declaration:
    return resolve(declared, settings, Lexicon(), defaults=DEFAULTS)


def test_the_settings_realtime_runs_the_voice_calls_and_the_classs_llm_the_written_ones(vendor: str) -> None:
    config = _tuned(AgentSettings(realtime=f"{vendor}/voice-3", realtime_options={"voice": "eve"}))
    assert config.realtime == Model(vendor, "voice-3", options={"voice": "eve"})
    assert config.llm == Model(ACME, "acme-1")


def test_a_vendor_alone_is_its_plugins_own_realtime_model(vendor: str) -> None:
    assert _tuned(AgentSettings(realtime=vendor)).realtime == Model(vendor, "")


def test_options_with_no_realtime_named_are_refused(vendor: str) -> None:
    with pytest.raises(ValidationError, match="named as vendor/model"):
        _tuned(AgentSettings(realtime_options={"voice": "eve"}))


def test_a_vendor_with_no_realtime_model_is_refused() -> None:
    with pytest.raises(ValidationError, match="acme has no model that hears and speaks itself"):
        _tuned(AgentSettings(realtime=f"{ACME}/acme-1"))


def test_the_settings_llm_never_names_a_realtime_model(vendor: str) -> None:
    with pytest.raises(ValidationError, match="it is the agent's realtime and not its llm"):
        _tuned(AgentSettings(llm=f"{vendor}/voice-3"), Declaration(slug="kala"))


def test_the_classs_realtime_wins_over_the_settings(vendor: str) -> None:
    declared = Declaration(slug="kala", realtime=Model(vendor, "voice-1"), fixed=frozenset({"realtime"}))
    assert _tuned(AgentSettings(realtime=f"{vendor}/voice-3"), declared).realtime == Model(vendor, "voice-1")


def test_the_classs_longest_call_and_timeout_win_over_the_settings_and_the_settings_fill_what_it_leaves() -> None:
    held = frozenset({"max_duration_s", "llm_timeout_s"})
    tuned = _tuned(
        AgentSettings(max_duration_s=300, llm_timeout_s=4.0),
        Declaration(slug="kala", max_duration_s=1200, llm_timeout_s=8.0, fixed=held),
    )
    assert (tuned.max_duration_s, tuned.llm_timeout_s) == (1200, 8.0)
    loose = _tuned(AgentSettings(max_duration_s=300, llm_timeout_s=4.0), Declaration(slug="kala"))
    assert (loose.max_duration_s, loose.llm_timeout_s) == (300, 4.0)


def test_the_settings_zone_is_the_agents_unless_its_class_declares_one() -> None:
    assert (
        _tuned(AgentSettings(timezone="America/Montevideo"), Declaration(slug="kala")).timezone == "America/Montevideo"
    )
    declared = Declaration(slug="kala", timezone="Europe/Madrid", fixed=frozenset({"timezone"}))
    assert _tuned(AgentSettings(timezone="America/Montevideo"), declared).timezone == "Europe/Madrid"
    assert _tuned(AgentSettings(), Declaration(slug="kala", timezone="Europe/Madrid")).timezone == "Europe/Madrid"


def test_a_zone_that_is_no_zone_is_refused() -> None:
    with pytest.raises(ValidationError, match="is not an IANA time zone"):
        parse_settings({"timezone": "Montevideo/Uruguay"})


def test_a_vendor_alone_names_no_model_to_think_with() -> None:
    """`--llm acme` is refused naming the form: a model is named, the ears and a voice have a default."""
    with pytest.raises(ValidationError, match=r"acme alone names no model: name it, `--llm acme/<model>`"):
        _tuned(AgentSettings(llm=ACME), Declaration(slug="kala"))


@pytest.mark.parametrize(
    "wrong",
    [
        lambda: check_idle(Idle(says=())),
        lambda: check_idle(Idle(says=("  ",))),
        lambda: check_idle(Idle(says=("Hello?",), after_s=4.0)),
        lambda: check_idle(Idle(says=("Hello?",), times=11)),
        lambda: check_voicemail(Voicemail(message=" ")),
        lambda: parse_settings({"silence_timeout_s": 4}),
        lambda: parse_settings({"tts_fallbacks": [""]}),
    ],
)
def test_the_quiet_a_machine_and_the_fallbacks_refuse_what_no_call_could_run(wrong: Callable[[], object]) -> None:
    with pytest.raises(ValidationError):
        wrong()


def test_what_the_class_declares_of_the_quiet_wins_over_the_settings_and_what_it_leaves_is_the_settings() -> None:
    fixed = Declaration(slug="a", silence_timeout_s=20, fixed=frozenset({"silence_timeout_s"}))
    assert _tuned(AgentSettings(silence_timeout_s=60), fixed).silence_timeout_s == 20
    assert _tuned(AgentSettings(silence_timeout_s=60), Declaration(slug="a")).silence_timeout_s == 60


def test_a_class_is_held_to_the_silence_a_setting_is() -> None:
    with pytest.raises(ValidationError, match="5 to 3600"):
        check_silence(1)


def test_a_classs_fallbacks_are_read_as_a_vendor_and_its_model() -> None:
    declared = declare(Declaration(slug="a"), Declared(stt_fallbacks=[ACME, f"{ACME}/one"]))
    assert declared.stt_fallbacks == (Model(vendor=ACME, model=""), Model(vendor=ACME, model="one"))
    assert declare(Declaration(slug="a"), Declared()).stt_fallbacks == ()


# Google retired the model its plugin runs when told none: a test room that set the temperature alone
# named the vendor with no model, and the pipeline (providers' test of it) must run the default's model.
def test_a_temperature_set_alone_names_the_defaults_vendor_with_no_model() -> None:
    thinking = _tuned(AgentSettings(temperature=0.2), Declaration(slug="front")).llm
    assert thinking is not None and (thinking.vendor, thinking.model, thinking.temperature) == (ACME, "", 0.2)
