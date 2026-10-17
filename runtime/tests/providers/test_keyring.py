"""A stage on its key carries the row's options and request for its model, on the box's key as on the org's."""

import pytest

from pinecall_runtime.agents.declaration import Model
from pinecall_runtime.exceptions import ServiceUnavailable
from pinecall_runtime.providers.schemas import Catalog
from pinecall_runtime.providers.service import Keyring, keyring, stage_on_its_key
from tests.conftest import configured
from tests.fakes import acme

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
