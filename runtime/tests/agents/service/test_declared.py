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
    MemoryConfig,
    ModelConfig,
    Pronunciation,
    VoiceConfig,
)
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


def test_a_voice_the_class_declares_names_its_vendor_and_the_voice() -> None:
    """A voice without its vendor, or without the voice, is refused naming the decorator."""
    with pytest.raises(ValidationError, match=r"@voice\('<vendor>', '<voice>'\)"):
        with_app_fields(NOTHING, Declared(voice=VoiceConfig(voice_id="v-1")))
    with pytest.raises(ValidationError, match="names its vendor and the voice"):
        with_app_fields(NOTHING, Declared(voice=VoiceConfig(provider=ACME)))


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


def test_the_judge_the_class_declares_is_a_model_and_is_fixed(listener: str) -> None:
    """A judge the class names is a model of a vendor that thinks, and it is fixed."""
    local = ModelConfig(provider=ACME, model="qwen3-32b", options={"base_url": "http://gpu/v1"})
    config = with_app_fields(NOTHING, Declared(judge=local))
    assert config.judge == Model(ACME, "qwen3-32b", options={"base_url": "http://gpu/v1"})
    assert config.fixed == frozenset({"judge"})
    with pytest.raises(ValidationError, match=f"{listener} has no llm"):
        with_app_fields(NOTHING, Declared(judge=ModelConfig(provider=listener, model="x")))
