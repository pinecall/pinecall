"""The pipeline report's reasons: a stage is unavailable when the call could not run it, on the model it would
run, and warned of when it runs but its ears do not hear the agent's language."""

from runtime.agents.declaration import Declaration
from runtime.agents.service.pipeline import list_unavailable, list_warnings
from runtime.providers.catalog import Catalog
from runtime.providers.service.keyring import Keyring
from runtime.providers.stage import Model
from tests.conftest import THE_CATALOG
from tests.fakes import acme

AGENT = Declaration(slug="front-desk")
THE_ROWS_MODELS = frozenset({f"{acme.ACME}/{acme.MODEL}", f"{acme.ACME}/{acme.EARS}", f"{acme.ACME}/{acme.VOICE}"})


def test_an_agent_that_names_nothing_runs_where_the_org_is_lent_the_rows_models_by_name() -> None:
    """A new org is lent models, not vendors: the stages left to the row are checked on the row's models, and run."""
    keys = Keyring(box={acme.ACME: "box-key"}, lends=THE_ROWS_MODELS)
    assert list_unavailable(AGENT, THE_CATALOG, keys) == {}


def test_a_stage_the_org_is_not_lent_is_said_with_what_it_may_run() -> None:
    """The voice's model lent to nobody is the one stage named, in the lending's own sentence."""
    keys = Keyring(box={acme.ACME: "box-key"}, lends=THE_ROWS_MODELS - {f"{acme.ACME}/{acme.VOICE}"})
    missing = list_unavailable(AGENT, THE_CATALOG, keys)
    assert list(missing) == ["speaks"]
    assert missing["speaks"].startswith(f"{acme.ACME}/{acme.VOICE} is not lent to this org")


def test_a_model_the_agent_names_is_the_one_checked_and_a_vendor_alone_runs_the_rows() -> None:
    """Named with a model nobody lends, the stage is unavailable; named by its vendor alone, it runs the row's model."""
    keys = Keyring(box={acme.ACME: "box-key"}, lends=THE_ROWS_MODELS)
    another = Declaration(slug="front-desk", llm=Model(vendor=acme.ACME, model="acme-nobody-lends"))
    assert list(list_unavailable(another, THE_CATALOG, keys)) == ["decides"]
    by_vendor = Declaration(slug="front-desk", llm=Model(vendor=acme.ACME, model=""))
    assert list_unavailable(by_vendor, THE_CATALOG, keys) == {}


def _hearing_two_languages() -> Catalog:
    row = THE_CATALOG.model_dump(mode="json")
    row["heard"] = {f"stt/{acme.ACME}/{acme.EARS}": ["en", "es"]}
    return Catalog.model_validate(row)


def test_ears_that_do_not_hear_the_agents_language_are_warned_of_with_what_fixes_it() -> None:
    """Named ears say to take them out; with none named and none listed that hear it, to name some that do."""
    catalog = _hearing_two_languages()
    named = Declaration(slug="front-desk", language="ar-EG", stt=Model(vendor=acme.ACME, model=acme.EARS))
    warned = list_warnings(named, catalog)
    assert list(warned) == ["hears"]
    assert warned["hears"].startswith(f"{acme.ACME}/{acme.EARS} does not hear ar (it hears en, es)")
    assert warned["hears"].endswith("take the transcriber out of its settings and Pinecall picks one that does")
    unnamed = list_warnings(Declaration(slug="front-desk", language="ar"), catalog)
    assert unnamed["hears"].endswith("no transcriber this runtime lists hears it: name one that does")


def test_a_language_the_ears_hear_or_one_nobody_set_is_warned_of_nothing() -> None:
    """Spanish is heard, no language is no promise, and ears the row lists nothing for hear what they are told."""
    catalog = _hearing_two_languages()
    assert list_warnings(Declaration(slug="front-desk", language="es"), catalog) == {}
    assert list_warnings(AGENT, catalog) == {}
    assert list_warnings(Declaration(slug="front-desk", language="ar"), THE_CATALOG) == {}
    row = catalog.model_dump(mode="json")
    row["ears"] = [{"vendor": acme.ACME, "model": "acme-ears-wide"}]
    assert list_warnings(Declaration(slug="front-desk", language="ar"), Catalog.model_validate(row)) == {}
