"""A stage on its key carries the row's options and request for its model, on the box's key as on the org's."""

from pinecall_runtime.agents.declaration import Model
from pinecall_runtime.providers.schemas import Catalog
from pinecall_runtime.providers.service import Keyring, stage_on_its_key
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
