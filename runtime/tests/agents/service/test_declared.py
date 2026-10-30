"""What a class declares: each field read into the config, fixed, and taken back when sent empty."""

import pytest

from pinecall_runtime.agents.declaration import AgentConfig, Docs, Greeting, MemoryPolicy, Model, Voice
from pinecall_runtime.agents.service.declared import with_app_fields
from pinecall_runtime.exceptions import ValidationError
from pinecall_runtime.providers.service import plugins
from pinecall_runtime.wire.parts import AgentConfig as Declared
from pinecall_runtime.wire.parts import (
    DocsConfig,
    GreetingConfig,
    HoldConfig,
    JudgeDeclaration,
    JudgesDeclared,
    MemoryConfig,
    ModelConfig,
    PersonaDeclaration,
    PersonasDeclared,
    PromptBlockSpec,
    Pronunciation,
    TurnConfig,
    VoiceConfig,
    WidgetLook,
)
from tests.fakes import talker
from tests.fakes.acme import ACME

NOTHING = AgentConfig(slug="clinica-norte")
# Vendors that do one stage alone, installed for the tests that need one.
THINKER = "thinker"
LISTENER = "listener"


@pytest.fixture
def thinker(monkeypatch: pytest.MonkeyPatch) -> str:
    """A vendor installed for this test alone, doing the llm stage and nothing else."""
    monkeypatch.setitem(plugins.installed(), THINKER, plugins.Vendor(THINKER, frozenset({"llm"})))
    return THINKER


@pytest.fixture
def listener(monkeypatch: pytest.MonkeyPatch) -> str:
    """A vendor installed for this test alone, doing the stt stage and nothing else."""
    monkeypatch.setitem(plugins.installed(), LISTENER, plugins.Vendor(LISTENER, frozenset({"stt"})))
    return LISTENER


def test_each_field_the_class_sends_becomes_the_configs_and_is_fixed() -> None:
    """Every field sent is read into the config and fixed against the org's settings."""
    declared = Declared(
        language="es",
        voice=VoiceConfig(provider=ACME, model="sonic-2", voice_id="v-1"),
        llm=ModelConfig(provider=ACME, model="acme-1", builds="responses.LLM", options={"use_websocket": True}),
        greeting=GreetingConfig(say="Hola."),
        says=[Pronunciation(word="GSA", spoken="G S A")],
        docs=DocsConfig(base="clinica", k=4),
        memory=MemoryConfig(remember=["allergies"]),
    )
    config = with_app_fields(NOTHING, declared)
    assert config.voice == Voice(ACME, "sonic-2", "v-1")
    assert config.llm == Model(ACME, "acme-1", builds="responses.LLM", options={"use_websocket": True})
    assert config.greeting == Greeting(say="Hola.")
    assert config.says == {"GSA": "G S A"}
    assert config.bases == (Docs(base="clinica", k=4),)
    assert config.memory == MemoryPolicy(remember=("allergies",))
    assert config.fixed == frozenset({"language", "voice", "llm", "greeting", "says", "docs", "memory"})


def test_a_field_sent_empty_goes_back_to_the_settings_and_one_left_out_stays_fixed() -> None:
    """Null gives a setting back to the org; a field the class left out stays as it was fixed."""
    current = AgentConfig(slug="clinica-norte", fixed=frozenset({"voice", "llm"}))
    assert with_app_fields(current, Declared(voice=None)).fixed == frozenset({"llm"})


def test_a_new_process_first_declaration_lets_go_of_what_the_one_before_it_fixed() -> None:
    """R F17: a save that took `language` out kept it fixed until `pinecall start` was restarted."""
    before = with_app_fields(NOTHING, Declared(language="en", llm=ModelConfig(provider=ACME, model="acme-1")))
    assert before.fixed == frozenset({"language", "llm"})
    after = with_app_fields(before, Declared(llm=ModelConfig(provider=ACME, model="acme-1")), first=True)
    assert (after.fixed, after.language) == (frozenset({"llm"}), None)
    assert with_app_fields(before, Declared(llm=ModelConfig(provider=ACME, model="acme-1"))).fixed == frozenset(
        {"language", "llm"}
    )


def test_a_field_sent_null_keeps_no_value_of_the_class_and_every_field_takes_null() -> None:
    """The value the class had fixed goes with it: the org's settings fill the field, not the class's last word."""
    declared = with_app_fields(NOTHING, Declared(language="fr-FR", record=False, uses_knowledge=True))
    assert (declared.language, declared.record, declared.uses_knowledge) == ("fr-FR", False, True)

    taken_back = with_app_fields(declared, Declared(language=None, record=None, uses_knowledge=None))
    assert (taken_back.language, taken_back.record, taken_back.uses_knowledge) == (None, True, False)
    assert taken_back.fixed == frozenset()


def test_a_voice_the_class_declares_names_its_vendor_and_the_voice() -> None:
    """A voice without its vendor, or without the voice, is refused naming the wire's fields and the decorator."""
    with pytest.raises(ValidationError, match=r"`provider` and `voice_id` \(or `name`\) on the wire, @voice\("):
        with_app_fields(NOTHING, Declared(voice=VoiceConfig(voice_id="v-1")))
    with pytest.raises(ValidationError, match="names its vendor and the voice"):
        with_app_fields(NOTHING, Declared(voice=VoiceConfig(provider=ACME)))


def test_a_static_block_after_a_dynamic_one_is_refused_by_name() -> None:
    """The static blocks are the cached prefix: the layout is every static block, then every dynamic one."""
    late = [PromptBlockSpec(name="view", region="dynamic"), PromptBlockSpec(name="rules", region="static")]
    with pytest.raises(ValidationError, match="static rules comes after a dynamic one"):
        with_app_fields(NOTHING, Declared(prompt=late))


def test_a_turn_threshold_outside_the_band_the_ears_take_is_refused_when_declared() -> None:
    """A class is held to the bands a setting is: outside one the ears refuse the connection."""
    with pytest.raises(ValidationError, match=r"eot_threshold 0\.95 is outside 0\.5 to 0\.9"):
        with_app_fields(NOTHING, Declared(turn=TurnConfig(eot_threshold=0.95)))
    with pytest.raises(ValidationError, match=r"eager_eot_threshold 0\.2 is outside 0\.3 to 0\.9"):
        with_app_fields(NOTHING, Declared(turn=TurnConfig(eager_eot_threshold=0.2)))


def test_a_vendor_not_installed_or_not_doing_the_stage_is_refused_when_declared(thinker: str) -> None:
    """A vendor this build lacks, or one that does not do the stage, is refused at declaration."""
    with pytest.raises(ValidationError, match="no vendor named 'acme-but-misspelt'"):
        with_app_fields(NOTHING, Declared(llm=ModelConfig(provider="acme-but-misspelt", model="x")))
    with pytest.raises(ValidationError, match=f"{thinker} has no stt"):
        with_app_fields(NOTHING, Declared(stt=ModelConfig(provider=thinker, model="x")))


def test_who_ends_the_turn_is_the_ears_and_refused_on_the_model() -> None:
    """end_of_turn belongs to the ears; set on the model it is refused."""
    ears = ModelConfig(provider=ACME, model="acme-ears", end_of_turn="smart-turn")
    assert with_app_fields(NOTHING, Declared(stt=ears)).stt == Model(ACME, "acme-ears", end_of_turn="smart-turn")
    with pytest.raises(ValidationError, match="end_of_turn is the ears'"):
        with_app_fields(NOTHING, Declared(llm=ModelConfig(provider=ACME, model="acme-1", end_of_turn="stt")))


def test_a_realtime_model_the_class_declares_is_fixed_beside_its_llm(monkeypatch: pytest.MonkeyPatch) -> None:
    """The voice calls' model and the written calls' are two settings, each fixed by the class."""
    vendor = talker.install(monkeypatch)
    declared = Declared(
        llm=ModelConfig(provider=ACME, model="acme-1"),
        realtime=ModelConfig(provider=vendor, model="voice-3", options={"voice": "eve"}),
    )
    config = with_app_fields(NOTHING, declared)
    assert config.llm == Model(ACME, "acme-1")
    assert config.realtime == Model(vendor, "voice-3", options={"voice": "eve"})
    assert config.fixed == frozenset({"llm", "realtime"})


def test_a_realtime_model_named_as_the_llm_is_refused_naming_the_realtime(monkeypatch: pytest.MonkeyPatch) -> None:
    """The llm answers the written calls, which a model that hears and speaks itself cannot."""
    vendor = talker.install(monkeypatch)
    with pytest.raises(ValidationError, match="it is the agent's realtime and not its llm"):
        with_app_fields(NOTHING, Declared(llm=ModelConfig(provider=vendor, model="voice-3")))
    with pytest.raises(ValidationError, match="it is the agent's realtime and not its llm"):
        with_app_fields(NOTHING, Declared(llm=ModelConfig(provider=vendor, model="x", builds="realtime.RealtimeModel")))


def test_a_realtime_model_is_a_vendors_that_has_one_and_takes_no_class_of_its_own(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A vendor with no realtime class is refused, and so is a class or a temperature named for one."""
    vendor = talker.install(monkeypatch)
    with pytest.raises(ValidationError, match="acme has no model that hears and speaks itself"):
        with_app_fields(NOTHING, Declared(realtime=ModelConfig(provider=ACME, model="acme-1")))
    with pytest.raises(ValidationError, match=r"@realtime\('<vendor>/<model>'"):
        with_app_fields(NOTHING, Declared(realtime=ModelConfig(provider=vendor, model="voice-3", builds="LLM")))


def test_the_judge_the_class_declares_is_a_model_and_is_fixed(listener: str) -> None:
    """A judge the class names is a model of a vendor that thinks, and it is fixed."""
    local = ModelConfig(provider=ACME, model="qwen3-32b", options={"base_url": "http://gpu/v1"})
    config = with_app_fields(NOTHING, Declared(judge=local))
    assert config.judge == Model(ACME, "qwen3-32b", options={"base_url": "http://gpu/v1"})
    assert config.fixed == frozenset({"judge"})
    with pytest.raises(ValidationError, match=f"{listener} has no llm"):
        with_app_fields(NOTHING, Declared(judge=ModelConfig(provider=listener, model="x")))


def test_the_longest_call_and_the_models_timeout_the_class_declares_are_fixed_and_held_to_their_bands() -> None:
    """Declared, both win over the settings; a limit outside 60 to 3600 (or 0) and a timeout of 0 are refused."""
    config = with_app_fields(NOTHING, Declared(max_duration_s=1200, llm_timeout_s=8.0))
    assert (config.max_duration_s, config.llm_timeout_s) == (1200, 8.0)
    assert config.fixed == frozenset({"max_duration_s", "llm_timeout_s"})
    let_go = with_app_fields(config, Declared(max_duration_s=None, llm_timeout_s=None))
    assert (let_go.max_duration_s, let_go.llm_timeout_s, let_go.fixed) == (600, None, frozenset())
    with pytest.raises(ValidationError, match="max_duration_s 30: 0 for no limit, or 60 to 3600 seconds"):
        with_app_fields(NOTHING, Declared(max_duration_s=30))
    with pytest.raises(ValidationError, match="llm_timeout_s is a positive number of seconds"):
        with_app_fields(NOTHING, Declared(llm_timeout_s=0))


def test_the_melody_and_the_widget_the_class_declares_are_fixed_and_held_to_the_doors_rules() -> None:
    """Declared, both are fixed; a wait out of its band and a look a widget would refuse are refused by sentence."""
    config = with_app_fields(NOTHING, Declared(hold=HoldConfig(after_s=1.5, off=True), widget=WidgetLook(title="Pip")))
    assert config.hold is not None and config.hold.after_s == 1.5 and config.hold.off
    assert config.widget is not None and config.widget.title == "Pip"
    assert config.fixed == frozenset({"hold", "widget"})
    with pytest.raises(ValidationError, match="after_s 31: the melody starts after 0 to 30 seconds"):
        with_app_fields(NOTHING, Declared(hold=HoldConfig(after_s=31)))
    with pytest.raises(ValidationError, match="a widget's title is 80 characters at most"):
        with_app_fields(NOTHING, Declared(widget=WidgetLook(title="x" * 81)))


def test_the_judges_and_the_personas_the_class_declares_are_fixed_and_let_go_when_sent_null() -> None:
    """Declared, the class owns both lists; sent null, the org writes them again."""
    judges = JudgesDeclared(on=["consent"], own=[JudgeDeclaration(name="offers-next-slot", question="Offered?")])
    personas = PersonasDeclared(own=[PersonaDeclaration(name="in-a-rush", goal="book today", style="short")])
    config = with_app_fields(NOTHING, Declared(judges=judges, personas=personas))
    assert (config.judges, config.personas) == (judges, personas)
    assert config.fixed == frozenset({"judges", "personas"})
    let_go = with_app_fields(config, Declared(judges=None))
    assert (let_go.judges, let_go.personas, let_go.fixed) == (None, personas, frozenset({"personas"}))
