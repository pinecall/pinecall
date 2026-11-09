"""The catalogue an org reads lists the realtime models each plugin names and, by stage, the models the org may pick."""

import dataclasses
import types
from typing import Literal

import pytest

from pinecall_runtime.providers import service as providers
from pinecall_runtime.providers.schemas import Catalog, Stage
from pinecall_runtime.providers.service import Keyring, catalog, keyring, plugins
from tests.conftest import configured
from tests.fakes import acme


def test_the_catalogue_lists_each_vendors_realtime_models_and_leaves_out_a_vendor_with_none(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    installed = plugins.installed()
    talking = dataclasses.replace(installed[acme.ACME], realtime=("voice-1", "voice-3"))
    # An LLM alone: nothing of it is imported to ask about its voices.
    silent = dataclasses.replace(installed[acme.ACME], name="quiet", does=frozenset({"llm"}))

    def two_vendors() -> dict[str, plugins.Vendor]:
        return {acme.ACME: talking, "quiet": silent}

    monkeypatch.setattr(plugins, "installed", two_vendors)
    listed = keyring.catalogue_of(configured(), Keyring(own={acme.ACME: "own-key"}))
    assert listed.realtime == {acme.ACME: ["voice-1", "voice-3"]}


OFFERED = {"stt/acme": ("acme-ears-2", "acme-ears-3"), "llm/acme": ("acme-2",)}


def offering() -> providers.Catalog:
    return configured().model_copy(update={"models": {"stt/acme": "acme-ears"}, "offered": OFFERED})


def test_the_catalogue_lists_the_rows_default_first_and_then_what_the_row_offers() -> None:
    listed = keyring.catalogue_of(offering(), Keyring(own={acme.ACME: "own-key"}))
    # The platform default's model leads its vendor's list, as it is what a call on it runs unpicked.
    assert set(listed.models) == {"stt/acme", "llm/acme"}
    assert listed.models["stt/acme"] == ["acme-ears", "acme-ears-2", "acme-ears-3"]
    assert listed.models["llm/acme"] == [acme.MODEL, "acme-2"]
    # Every installed plugin's own default is in `runs` beside it; the row's word is acme's.
    assert listed.runs["stt/acme"] == "acme-ears"


def test_where_the_row_names_no_model_the_plugins_own_runs_and_comes_first(monkeypatch: pytest.MonkeyPatch) -> None:
    installed = plugins.installed()
    says = dataclasses.replace(installed[acme.ACME], defaults={"llm": "acme-9", "stt": "acme-ears-9"})
    monkeypatch.setattr(plugins, "installed", lambda: {acme.ACME: says})
    row = offering()
    unnamed = row.model_copy(update={"defaults": {**row.defaults, "llm": Stage(vendor=acme.ACME)}})
    listed = keyring.catalogue_of(unnamed, Keyring(own={acme.ACME: "own-key"}))
    # The row's word wins over the plugin's for the ears; with no model anywhere, the plugin's stands.
    assert listed.runs["stt/acme"] == "acme-ears"
    assert listed.runs["llm/acme"] == "acme-9"
    assert listed.models["llm/acme"] == ["acme-9", "acme-2"]


def test_the_default_vendor_runs_the_defaults_model_and_never_the_plugins_own(monkeypatch: pytest.MonkeyPatch) -> None:
    """Google's plugin builds a model Google retired; the platform default names another, and a call runs that."""
    installed = plugins.installed()
    says = dataclasses.replace(installed[acme.ACME], defaults={"llm": "acme-retired"})
    monkeypatch.setattr(plugins, "installed", lambda: {acme.ACME: says})
    listed = keyring.catalogue_of(offering(), Keyring(own={acme.ACME: "own-key"}))
    assert listed.runs["llm/acme"] == acme.MODEL
    assert listed.models["llm/acme"] == [acme.MODEL, "acme-2"]


def test_an_org_lent_one_model_of_a_vendor_is_offered_that_model_alone_and_the_vendor_with_it() -> None:
    lent = Keyring(box={acme.ACME: "box-key"}, lends=frozenset({"acme/acme-ears-3", "acme/acme-5"}))
    listed = keyring.catalogue_of(offering(), lent)
    assert listed.models == {"stt/acme": ["acme-ears-3"]}
    assert [one.availability for one in listed.providers if one.name == acme.ACME] == ["offered"]


def test_an_org_lent_nothing_of_a_vendor_is_offered_none_of_its_models() -> None:
    listed = keyring.catalogue_of(offering(), Keyring(box={acme.ACME: "box-key"}, lends=frozenset()))
    assert listed.models == {}
    assert [one.availability for one in listed.providers if one.name == acme.ACME] == ["bring your own"]


def leading() -> providers.Catalog:
    return offering().model_copy(
        update={
            "recommended": {"stt/acme": ("acme-ears-3",)},
            "names": {"acme/acme-ears-3": "Acme Ears 3"},
            "rates": {
                "acme-ears": providers.Rate(audio_seconds=0.0001),
                "acme-2": providers.Rate(input=1.0, output=4.0),
            },
        }
    )


def test_the_choices_list_every_model_the_row_offers_the_recommended_first_named_and_priced() -> None:
    listed = keyring.catalogue_of(leading(), Keyring(own={acme.ACME: "own-key"}))
    ears = listed.choices["stt/acme"]
    assert [one.model for one in ears] == ["acme-ears-3", "acme-ears", "acme-ears-2"]
    assert [one.recommended for one in ears] == [True, False, False]
    assert ears[0].name == "Acme Ears 3"
    # Priced by the longest prefix of the id, as a call is: the family's rate reaches each snapshot.
    assert ears[1].price is not None and ears[1].price.audio_seconds == 0.0001
    assert ears[0].price is not None and ears[0].price.audio_seconds == 0.0001
    assert listed.choices["llm/acme"][1].price is not None and listed.choices["llm/acme"][1].price.output == 4.0
    # On the org's own key, every one may run.
    assert all(one.available for one in ears)


def test_the_choices_say_which_models_the_org_may_run_on_the_boxs_key_and_keep_the_rest_greyed() -> None:
    lent = Keyring(box={acme.ACME: "box-key"}, lends=frozenset({"acme/acme-ears-3"}))
    listed = keyring.catalogue_of(leading(), lent)
    assert {one.model: one.available for one in listed.choices["stt/acme"]} == {
        "acme-ears-3": True,
        "acme-ears": False,
        "acme-ears-2": False,
    }
    # `models` stays what the org may run, alone, for the CLI and the older console.
    assert listed.models == {"stt/acme": ["acme-ears-3"]}
    # A box with no key for the vendor lends none of it.
    unkeyed = keyring.catalogue_of(leading(), Keyring())
    assert not any(one.available for one in unkeyed.choices["stt/acme"])


class _Ears:
    """The plugin's own ears, typing the models they run, as Deepgram's `STT` does."""

    def __init__(self, *, model: Literal["nova-1", "nova-2"] | str = "nova-2") -> None:
        self.model = model


class _Flux:
    """A second class of ears that ends the turn itself, running the models it lists, as Deepgram's `STTv2`."""

    def __init__(self, *, model: Literal["flux-en", "flux-multi"] | str = "flux-en") -> None:
        self.model = model


def test_the_class_the_row_names_runs_the_models_it_lists_and_the_plugins_own_class_runs_the_rest(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Deepgram's `nova-3` was built as `STTv2`, Flux's door, and refused at the socket: it runs on `STT`,
    which ends no turn; a model neither lists is the row's word."""

    def deepgram_like(_vendor: str) -> types.SimpleNamespace:
        return types.SimpleNamespace(STT=_Ears, STTv2=_Flux)

    monkeypatch.setattr(catalog, "plugin", deepgram_like)
    row = configured().model_dump(mode="json")
    row["tuning"][f"stt/{acme.ACME}"] = {"builds": "STTv2", "ends_the_turn": True}
    written = Catalog.model_validate(row)
    flux = catalog.tuning_of(written, "stt", acme.ACME, "flux-multi")
    assert flux is not None and flux.builds == "STTv2" and flux.ends_the_turn
    nova = catalog.tuning_of(written, "stt", acme.ACME, "nova-1")
    assert nova is not None and nova.builds is None and not nova.ends_the_turn
    unknown = catalog.tuning_of(written, "stt", acme.ACME, "whisper-9")
    assert unknown is not None and unknown.builds == "STTv2" and unknown.ends_the_turn
    unnamed = catalog.tuning_of(written, "stt", acme.ACME, None)
    assert unnamed is not None and unnamed.builds == "STTv2"
