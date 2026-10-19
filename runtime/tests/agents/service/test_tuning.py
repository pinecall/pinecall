"""The settings' realtime model is laid over the declaration beside its llm: named `vendor/model` or a
vendor alone, with its options, and never in the llm's place; a class's own wins over it."""

import pytest

from pinecall_runtime.agents.declaration import AgentConfig, Lexicon, Modality, Model, Tuning
from pinecall_runtime.agents.service.tuning import apply_tuning
from pinecall_runtime.exceptions import ValidationError
from tests.fakes import talker
from tests.fakes.acme import ACME

DEFAULTS: dict[Modality, str] = {"llm": ACME, "stt": ACME, "tts": ACME}
DECLARED = AgentConfig(slug="kala", llm=Model(ACME, "acme-1"), fixed=frozenset({"llm"}))


@pytest.fixture
def vendor(monkeypatch: pytest.MonkeyPatch) -> str:
    """The talker vendor, installed for this test alone."""
    return talker.install(monkeypatch)


def _tuned(tuning: Tuning, declared: AgentConfig = DECLARED) -> AgentConfig:
    return apply_tuning(declared, tuning, Lexicon(), defaults=DEFAULTS)


def test_the_settings_realtime_runs_the_voice_calls_and_the_classs_llm_the_written_ones(vendor: str) -> None:
    config = _tuned(Tuning(realtime=f"{vendor}/voice-3", realtime_options={"voice": "eve"}))
    assert config.realtime == Model(vendor, "voice-3", options={"voice": "eve"})
    assert config.llm == Model(ACME, "acme-1")


def test_a_vendor_alone_is_its_plugins_own_realtime_model(vendor: str) -> None:
    assert _tuned(Tuning(realtime=vendor)).realtime == Model(vendor, "")


def test_options_with_no_realtime_named_are_refused(vendor: str) -> None:
    with pytest.raises(ValidationError, match="named as vendor/model"):
        _tuned(Tuning(realtime_options={"voice": "eve"}))


def test_a_vendor_with_no_realtime_model_is_refused() -> None:
    with pytest.raises(ValidationError, match="acme has no model that hears and speaks itself"):
        _tuned(Tuning(realtime=f"{ACME}/acme-1"))


def test_the_settings_llm_never_names_a_realtime_model(vendor: str) -> None:
    with pytest.raises(ValidationError, match="it is the agent's realtime and not its llm"):
        _tuned(Tuning(llm=f"{vendor}/voice-3"), AgentConfig(slug="kala"))


def test_the_classs_realtime_wins_over_the_settings(vendor: str) -> None:
    declared = AgentConfig(slug="kala", realtime=Model(vendor, "voice-1"), fixed=frozenset({"realtime"}))
    assert _tuned(Tuning(realtime=f"{vendor}/voice-3"), declared).realtime == Model(vendor, "voice-1")
