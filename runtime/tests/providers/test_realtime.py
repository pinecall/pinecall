"""A realtime model is built by its plugin's realtime class, with its key, its model and its options,
whatever the row names for the vendor's LLM; a vendor with no such class has none, and an LLM stage
never names one."""

import pytest

from pinecall_runtime.exceptions import ValidationError
from pinecall_runtime.providers.service import plugins, stages
from pinecall_runtime.providers.service.plugins import Running
from tests.fakes import talker
from tests.fakes.acme import ACME


@pytest.fixture
def vendor(monkeypatch: pytest.MonkeyPatch) -> str:
    """The talker vendor, installed for this test alone."""
    return talker.install(monkeypatch)


def test_the_realtime_class_is_built_with_the_key_the_model_and_the_options(vendor: str) -> None:
    running = Running(vendor=vendor, credentials="k", model="voice-3", builds="LLM", options={"voice": "eve"})
    built = stages.build_realtime(running)
    assert isinstance(built, talker.TalkerRealtime)
    assert built.given == {"api_key": "k", "model": "voice-3", "voice": "eve"}


def test_a_vendor_alone_builds_its_plugins_own_realtime_model(vendor: str) -> None:
    built = stages.build_realtime(Running(vendor=vendor, credentials="k"))
    assert isinstance(built, talker.TalkerRealtime)
    assert built.given["model"] == "voice-1"


def test_a_vendor_with_no_realtime_class_has_no_realtime_model() -> None:
    with pytest.raises(ValidationError, match="acme has no model that hears and speaks itself"):
        stages.build_realtime(Running(vendor=ACME, credentials="k", model="acme-1"))


def test_an_llm_that_names_a_realtime_model_or_its_class_is_refused_naming_the_realtime(vendor: str) -> None:
    with pytest.raises(ValidationError, match=r"talker/voice-3 hears and speaks itself.*@realtime"):
        plugins.refuse_realtime_as_llm(vendor, "voice-3", None)
    with pytest.raises(ValidationError, match="hears and speaks itself"):
        plugins.refuse_realtime_as_llm(vendor, talker.PLAIN, "realtime.RealtimeModel")
    plugins.refuse_realtime_as_llm(vendor, talker.PLAIN, None)
