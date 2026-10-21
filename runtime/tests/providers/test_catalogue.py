"""The catalogue an org reads lists the realtime models each plugin names and, by stage, the models the org may pick."""

import dataclasses

import pytest

from pinecall_runtime.providers import service as providers
from pinecall_runtime.providers.service import Keyring, keyring, plugins
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
    assert listed.models == {"stt/acme": ["acme-ears", "acme-ears-2", "acme-ears-3"], "llm/acme": ["acme-2"]}


def test_an_org_lent_one_model_of_a_vendor_is_offered_that_model_alone_and_the_vendor_with_it() -> None:
    lent = Keyring(box={acme.ACME: "box-key"}, lends=frozenset({"acme/acme-ears-3", "acme/acme-5"}))
    listed = keyring.catalogue_of(offering(), lent)
    assert listed.models == {"stt/acme": ["acme-ears-3"]}
    assert [one.availability for one in listed.providers if one.name == acme.ACME] == ["offered"]


def test_an_org_lent_nothing_of_a_vendor_is_offered_none_of_its_models() -> None:
    listed = keyring.catalogue_of(offering(), Keyring(box={acme.ACME: "box-key"}, lends=frozenset()))
    assert listed.models == {}
    assert [one.availability for one in listed.providers if one.name == acme.ACME] == ["bring your own"]
