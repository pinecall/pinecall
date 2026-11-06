"""A stage on its key carries the row's options and request for its model, on the box's key as on the org's;
a realtime model runs on the org's own alone."""

import pytest

from pinecall_runtime.agents.declaration import AgentConfig, Model, Tuning
from pinecall_runtime.agents.service.tuning import _thinking
from pinecall_runtime.exceptions import Conflict, ServiceUnavailable
from pinecall_runtime.providers.schemas import Catalog
from pinecall_runtime.providers.service import Keyring, keyring, stage_on_its_key
from tests.conftest import configured
from tests.fakes import acme, talker

THE_ROWS_OPTIONS = {"max_tokens": 4096, "caching": "ephemeral"}
THE_ROWS_REQUEST = {"output_config": {"effort": "low"}}


def _tuned() -> Catalog:
    row = configured().model_dump(mode="json")
    row["tuning"][f"llm/{acme.ACME}/{acme.MODEL}"] = {"options": THE_ROWS_OPTIONS, "request": THE_ROWS_REQUEST}
    return Catalog.model_validate(row)


def test_the_boxs_key_runs_the_model_with_the_rows_options_as_the_orgs_own_does() -> None:
    """The judge on the box's key is built like any stage: its ceiling, its caching and its effort apply."""
    named = Model(provider=acme.ACME, model=acme.MODEL)
    lent = stage_on_its_key("llm", named, _tuned(), Keyring(box={acme.ACME: "box-key"}))
    own = stage_on_its_key("llm", named, _tuned(), Keyring(own={acme.ACME: "own-key"}))
    assert lent.lent and not own.lent
    assert lent.options == own.options == THE_ROWS_OPTIONS
    assert lent.request == own.request == THE_ROWS_REQUEST


# An open model run in this process (a livekit plugin whose classes take no key) needs no key of the
# org's nor the box's: the keyring runs it on none instead of refusing the call.
def test_a_vendor_whose_plugin_takes_no_key_runs_on_none(monkeypatch: pytest.MonkeyPatch) -> None:
    assert keyring.takes_a_key("acme") is True
    with pytest.raises(ServiceUnavailable, match="acme has no key"):
        keyring.running_on(keyring.Keyring(), "acme", None)

    def never(_vendor: str) -> bool:
        return False

    monkeypatch.setattr(keyring, "takes_a_key", never)
    ran = keyring.running_on(keyring.Keyring(), "acme", "acme-1")
    assert (ran.vendor, ran.credentials, ran.model, ran.lent) == ("acme", "", "acme-1", False)


# A realtime model runs on the org's own key alone, as a plugin's own class does; told the agent's options.
def test_a_realtime_model_runs_on_the_orgs_own_key_with_its_options_and_never_on_a_lent_one(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    vendor = talker.install(monkeypatch)
    named = Model(provider=vendor, model="voice-3", options={"voice": "eve"})
    own = keyring.talking_of(named, Keyring(own={vendor: "own-key"}))
    assert (own.credentials, own.model, own.options, own.lent) == ("own-key", "voice-3", {"voice": "eve"}, False)
    with pytest.raises(Conflict, match=f"runs on the org's own {vendor} key"):
        keyring.talking_of(named, Keyring(box={vendor: "box-key"}))


def test_the_pipeline_carries_the_realtime_model_beside_the_llm_where_the_agent_names_one(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    vendor = talker.install(monkeypatch)
    keys = Keyring(own={acme.ACME: "acme-key", vendor: "own-key"})
    plain = AgentConfig(slug="kala")
    talking = AgentConfig(slug="kala", realtime=Model(provider=vendor, model="voice-3"))
    assert keyring.build_pipeline(plain, configured(), keys).realtime is None
    built = keyring.build_pipeline(talking, configured(), keys)
    assert built.realtime is not None
    assert (built.realtime.vendor, built.realtime.model, built.llm.vendor) == (vendor, "voice-3", acme.ACME)


# Google retired gemini-2.5-flash under "new users", the model its plugin runs when told none: a test
# room that sets only the temperature named the vendor alone, and every call of it died at the first turn.
def test_a_vendor_named_alone_runs_the_defaults_model_where_the_default_is_that_vendor() -> None:
    """No model and no `models` row: the default's model, never the plugin's own; another vendor's stays None."""
    alone = Model(provider=acme.ACME, model="")
    ran = stage_on_its_key("llm", alone, _tuned(), Keyring(box={acme.ACME: "box-key"}))
    assert ran.model == acme.MODEL
    row = _tuned().model_dump(mode="json")
    row["defaults"]["llm"] = {"vendor": "other", "model": "other-1"}
    on_another = stage_on_its_key("llm", alone, Catalog.model_validate(row), Keyring(box={acme.ACME: "box-key"}))
    assert on_another.model is None


# The production symptom whole: a test room that sets the temperature alone, the agent on the default's
# vendor, names that vendor with no model; the pipeline runs the default's model, not the plugin's own.
def test_a_test_room_that_sets_the_temperature_alone_runs_the_defaults_model() -> None:
    thinking = _thinking(AgentConfig(slug="front"), Tuning(temperature=0.2), {"llm": acme.ACME})
    assert thinking is not None and (thinking.provider, thinking.model) == (acme.ACME, "")
    config = AgentConfig(slug="front", llm=thinking)
    pipeline = keyring.build_pipeline(config, _tuned(), Keyring(box={acme.ACME: "box-key"}))
    assert (pipeline.llm.model, pipeline.llm.options["temperature"]) == (acme.MODEL, 0.2)
