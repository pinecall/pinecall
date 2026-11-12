"""What an org can run lists the realtime models each plugin names and, by stage, the models the org may pick."""

import dataclasses

from runtime.enums import Stage
from runtime.providers.catalog import Catalog, Rate, StageChoice
from runtime.providers.service import plugins, readiness
from runtime.providers.service.keyring import Keyring
from tests.conftest import configured
from tests.fakes import acme

# The vendors a process has installed, as the tests name them: acme alone.
ACME_ALONE = {acme.ACME: plugins.list_vendors()[acme.ACME]}


def test_the_catalogue_lists_each_vendors_realtime_models_and_leaves_out_a_vendor_with_none() -> None:
    talking = dataclasses.replace(ACME_ALONE[acme.ACME], realtime=("voice-1", "voice-3"))
    # An LLM alone: nothing of it is imported to ask about its voices.
    silent = dataclasses.replace(ACME_ALONE[acme.ACME], name="quiet", does=frozenset({Stage.llm}))
    two_vendors = {acme.ACME: talking, "quiet": silent}
    listed = readiness.runnable_on(configured(), Keyring(own={acme.ACME: "own-key"}), two_vendors)
    assert listed.realtime == {acme.ACME: ["voice-1", "voice-3"]}


OFFERED = {"stt/acme": ("acme-ears-2", "acme-ears-3"), "llm/acme": ("acme-2",)}


def offering() -> Catalog:
    return configured().model_copy(update={"models": {"stt/acme": "acme-ears"}, "offered": OFFERED})


def test_the_catalogue_lists_the_rows_default_first_and_then_what_the_row_offers() -> None:
    listed = readiness.runnable_on(offering(), Keyring(own={acme.ACME: "own-key"}), ACME_ALONE)
    # The platform default's model leads its vendor's list, as it is what a call on it runs unpicked.
    assert set(listed.models) == {"stt/acme", "llm/acme"}
    assert listed.models["stt/acme"] == ["acme-ears", "acme-ears-2", "acme-ears-3"]
    assert listed.models["llm/acme"] == [acme.MODEL, "acme-2"]
    # Every installed plugin's own default is in `runs` beside it; the row's word is acme's.
    assert listed.runs["stt/acme"] == "acme-ears"


def test_where_the_row_names_no_model_the_plugins_own_runs_and_comes_first() -> None:
    says = dataclasses.replace(ACME_ALONE[acme.ACME], defaults={Stage.llm: "acme-9", Stage.stt: "acme-ears-9"})
    row = offering()
    unnamed = row.model_copy(update={"defaults": {**row.defaults, Stage.llm: StageChoice(vendor=acme.ACME)}})
    listed = readiness.runnable_on(unnamed, Keyring(own={acme.ACME: "own-key"}), {acme.ACME: says})
    # The row's word wins over the plugin's for the ears; with no model anywhere, the plugin's stands.
    assert listed.runs["stt/acme"] == "acme-ears"
    assert listed.runs["llm/acme"] == "acme-9"
    assert listed.models["llm/acme"] == ["acme-9", "acme-2"]


def test_the_default_vendor_runs_the_defaults_model_and_never_the_plugins_own() -> None:
    """Google's plugin builds a model Google retired; the platform default names another, and a call runs that."""
    says = dataclasses.replace(ACME_ALONE[acme.ACME], defaults={Stage.llm: "acme-retired"})
    listed = readiness.runnable_on(offering(), Keyring(own={acme.ACME: "own-key"}), {acme.ACME: says})
    assert listed.runs["llm/acme"] == acme.MODEL
    assert listed.models["llm/acme"] == [acme.MODEL, "acme-2"]


def test_an_org_lent_one_model_of_a_vendor_is_offered_that_model_alone_and_the_vendor_with_it() -> None:
    lent = Keyring(box={acme.ACME: "box-key"}, lends=frozenset({"acme/acme-ears-3", "acme/acme-5"}))
    listed = readiness.runnable_on(offering(), lent, ACME_ALONE)
    assert listed.models == {"stt/acme": ["acme-ears-3"]}
    assert [one.availability for one in listed.providers if one.name == acme.ACME] == ["offered"]


def test_an_org_lent_nothing_of_a_vendor_is_offered_none_of_its_models() -> None:
    listed = readiness.runnable_on(offering(), Keyring(box={acme.ACME: "box-key"}, lends=frozenset()), ACME_ALONE)
    assert listed.models == {}
    assert [one.availability for one in listed.providers if one.name == acme.ACME] == ["bring your own"]


def leading() -> Catalog:
    return offering().model_copy(
        update={
            "recommended": {"stt/acme": ("acme-ears-3",)},
            "names": {"acme/acme-ears-3": "Acme Ears 3"},
            "rates": {
                "acme-ears": Rate(audio_seconds=0.0001),
                "acme-2": Rate(input=1.0, output=4.0),
            },
        }
    )


def test_the_choices_list_every_model_the_row_offers_the_recommended_first_named_and_priced() -> None:
    listed = readiness.runnable_on(leading(), Keyring(own={acme.ACME: "own-key"}), ACME_ALONE)
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
    listed = readiness.runnable_on(leading(), lent, ACME_ALONE)
    assert {one.model: one.available for one in listed.choices["stt/acme"]} == {
        "acme-ears-3": True,
        "acme-ears": False,
        "acme-ears-2": False,
    }
    # `models` stays what the org may run, alone, for the CLI and the older console.
    assert listed.models == {"stt/acme": ["acme-ears-3"]}
    # A box with no key for the vendor lends none of it.
    unkeyed = readiness.runnable_on(leading(), Keyring(), ACME_ALONE)
    assert not any(one.available for one in unkeyed.choices["stt/acme"])
