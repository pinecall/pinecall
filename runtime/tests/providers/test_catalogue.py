"""The catalogue an org reads lists, by vendor, the models that hear and speak themselves, as each plugin names them."""

import dataclasses

import pytest

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
