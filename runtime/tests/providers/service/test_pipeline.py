"""A stage on its key carries the row's options and request for its model, on the box's key as on the org's;
a realtime model runs on the org's own alone; an agent's fallbacks take the place of the stage's."""

from collections.abc import Sequence
from dataclasses import dataclass

import pytest

from runtime.enums import Stage
from runtime.exceptions import Conflict, ServiceUnavailable
from runtime.providers.catalog import Catalog
from runtime.providers.service import keyring, pipeline
from runtime.providers.service.keyring import Keyring
from runtime.providers.stage import Model, Voice
from tests.conftest import configured
from tests.fakes import acme, talker
from tests.fakes.plugins import install_plugin

THE_ROWS_OPTIONS = {"max_tokens": 4096, "caching": "ephemeral"}
THE_ROWS_REQUEST = {"output_config": {"effort": "low"}}


@dataclass(frozen=True)
class Stages:
    """What an agent's declaration says of its stages: nothing but what a test names."""

    language: str | None = None
    llm: Model | None = None
    stt: Model | None = None
    voice: Voice | None = None
    judge: Model | None = None
    realtime: Model | None = None
    stt_fallbacks: Sequence[Model] = ()
    tts_fallbacks: Sequence[Model] = ()


def _tuned() -> Catalog:
    row = configured().model_dump(mode="json")
    row["tuning"][f"llm/{acme.ACME}/{acme.MODEL}"] = {"options": THE_ROWS_OPTIONS, "request": THE_ROWS_REQUEST}
    return Catalog.model_validate(row)


def test_the_boxs_key_runs_the_model_with_the_rows_options_as_the_orgs_own_does() -> None:
    """The judge on the box's key is built like any stage: its ceiling, its caching and its effort apply."""
    named = Model(vendor=acme.ACME, model=acme.MODEL)
    lent = pipeline.stage_on_its_key(Stage.llm, named, _tuned(), Keyring(box={acme.ACME: "box-key"}))
    own = pipeline.stage_on_its_key(Stage.llm, named, _tuned(), Keyring(own={acme.ACME: "own-key"}))
    assert lent.lent and not own.lent
    assert lent.options == own.options == THE_ROWS_OPTIONS
    assert lent.request == own.request == THE_ROWS_REQUEST


# An open model run in this process (a livekit plugin whose classes take no key) needs no key of the
# org's nor the box's: the keyring runs it on none instead of refusing the call.
class OpenLLM:
    """A model this process runs itself: its class takes a model and no key."""

    def __init__(self, *, model: str = "open-1") -> None:
        self.model = model


OPEN = install_plugin("open", LLM=OpenLLM)


def test_a_vendor_whose_plugin_takes_no_key_runs_on_none() -> None:
    assert keyring.takes_a_key("acme") is True
    with pytest.raises(ServiceUnavailable, match="acme has no key"):
        keyring.running_on(Keyring(), "acme", None)
    assert keyring.takes_a_key(OPEN) is False
    ran = keyring.running_on(Keyring(), OPEN, "open-1")
    assert (ran.vendor, ran.credentials, ran.model, ran.lent) == (OPEN, "", "open-1", False)


# A realtime model runs on the org's own key alone, as a plugin's own class does; told the agent's options.
def test_a_realtime_model_runs_on_the_orgs_own_key_with_its_options_and_never_on_a_lent_one() -> None:
    vendor = talker.install()
    named = Model(vendor=vendor, model="voice-3", options={"voice": "eve"})
    own = pipeline.talking_of(named, Keyring(own={vendor: "own-key"}))
    assert (own.credentials, own.model, own.options, own.lent) == ("own-key", "voice-3", {"voice": "eve"}, False)
    with pytest.raises(Conflict, match=f"runs on the org's own {vendor} key"):
        pipeline.talking_of(named, Keyring(box={vendor: "box-key"}))


def test_the_pipeline_carries_the_realtime_model_beside_the_llm_where_the_agent_names_one() -> None:
    vendor = talker.install()
    keys = Keyring(own={acme.ACME: "acme-key", vendor: "own-key"})
    assert pipeline.build_pipeline(Stages(), configured(), keys).realtime is None
    built = pipeline.build_pipeline(Stages(realtime=Model(vendor=vendor, model="voice-3")), configured(), keys)
    assert built.realtime is not None
    assert (built.realtime.vendor, built.realtime.model, built.llm.vendor) == (vendor, "voice-3", acme.ACME)


# Google retired gemini-2.5-flash under "new users", the model its plugin runs when told none: a test
# room that sets only the temperature named the vendor alone, and every call of it died at the first turn.
def test_a_vendor_named_alone_runs_the_defaults_model_where_the_default_is_that_vendor() -> None:
    """No model and no `models` row: the default's model, never the plugin's own; another vendor's stays None."""
    alone = Model(vendor=acme.ACME, model="")
    ran = pipeline.stage_on_its_key(Stage.llm, alone, _tuned(), Keyring(box={acme.ACME: "box-key"}))
    assert ran.model == acme.MODEL
    row = _tuned().model_dump(mode="json")
    row["defaults"]["llm"] = {"vendor": "other", "model": "other-1"}
    keys = Keyring(box={acme.ACME: "box-key"})
    assert pipeline.stage_on_its_key(Stage.llm, alone, Catalog.model_validate(row), keys).model is None


# The production symptom whole: a test room that sets the temperature alone, the agent on the default's
# vendor, names that vendor with no model; the pipeline runs the default's model, not the plugin's own.
def test_a_test_room_that_sets_the_temperature_alone_runs_the_defaults_model() -> None:
    thinking = Stages(llm=Model(vendor=acme.ACME, model="", temperature=0.2))
    built = pipeline.build_pipeline(thinking, _tuned(), Keyring(box={acme.ACME: "box-key"}))
    assert (built.llm.model, built.llm.options["temperature"]) == (acme.MODEL, 0.2)


def test_an_agents_own_fallbacks_take_the_place_of_the_stages_and_one_with_no_key_is_left_out() -> None:
    keys = Keyring(
        box={acme.ACME: "box-key"},
        lends=frozenset({f"{acme.ACME}/{acme.MODEL}", f"{acme.ACME}/{acme.EARS}", f"{acme.ACME}/{acme.VOICE}"}),
    )
    unlent = Model(vendor=acme.ACME, model="acme-ears-nobody-lends")
    named = (unlent, Model(vendor=acme.ACME, model=acme.EARS))
    assert pipeline.build_pipeline(Stages(), _tuned(), keys).stt.fallbacks == ()
    backed = pipeline.build_pipeline(Stages(stt_fallbacks=named), _tuned(), keys)
    assert [one.model for one in backed.stt.fallbacks] == [acme.EARS]


WIDE_EARS = "acme-ears-wide"


def _by_language() -> Catalog:
    row = configured().model_dump(mode="json")
    row["heard"] = {f"stt/{acme.ACME}/{acme.EARS}": ["en", "es"]}
    row["ears"] = [{"vendor": acme.ACME, "model": WIDE_EARS}]
    row["hints"] = ["es", "en"]
    return Catalog.model_validate(row)


# Deepgram's Flux hears ten languages and wrote a call in Arabic as English that sounds alike: the agent
# read "Detail it Morattossel" and said it could not hear (2026-11-17).
def test_a_call_in_a_language_the_defaults_ears_do_not_hear_runs_the_ears_that_do() -> None:
    """Spanish and no language stay on the default's ears; Arabic, by any tag, runs the row's ears for the rest."""
    keys = Keyring(box={acme.ACME: "box-key"})
    assert pipeline.build_pipeline(Stages(language="es"), _by_language(), keys).stt.model == acme.EARS
    assert pipeline.build_pipeline(Stages(), _by_language(), keys).stt.model == acme.EARS
    arabic = pipeline.build_pipeline(Stages(language="ar-EG"), _by_language(), keys).stt
    assert (arabic.model, arabic.language, arabic.hints) == (WIDE_EARS, "ar", ("ar", "es", "en"))


def test_ears_an_agent_names_stay_its_own_and_are_told_the_languages_they_hear_alone() -> None:
    """Named ears are never swapped; a hint they do not hear is not sent, since the vendor refuses it."""
    keys = Keyring(box={acme.ACME: "box-key"})
    named = Stages(language="ar", stt=Model(vendor=acme.ACME, model=acme.EARS))
    ears = pipeline.build_pipeline(named, _by_language(), keys).stt
    assert (ears.model, ears.hints) == (acme.EARS, ("es", "en"))


def test_a_language_no_listed_ears_hear_stays_on_the_defaults() -> None:
    """With nothing else to run, the default's ears take the call: the report warns, the call is not refused."""
    row = _by_language().model_dump(mode="json")
    row["heard"][f"stt/{acme.ACME}/{WIDE_EARS}"] = ["ar"]
    keys = Keyring(box={acme.ACME: "box-key"})
    assert pipeline.build_pipeline(Stages(language="hi"), Catalog.model_validate(row), keys).stt.model == acme.EARS
