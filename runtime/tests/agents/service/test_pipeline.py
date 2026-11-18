"""The pipeline report's reasons: a stage is unavailable when the call could not run it, on the model it would
run, and warned of when it runs but its ears do not hear the agent's language."""

from runtime.agents.declaration import Declaration
from runtime.agents.service.pipeline import list_unavailable, list_warnings
from runtime.providers.catalog import Catalog
from runtime.providers.service.keyring import Keyring
from runtime.providers.stage import Model, Voice
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


ALL_OF_ACME = Keyring(box={acme.ACME: "box-key"})
WIDE_EARS = "acme-ears-wide"
ANOTHER = acme.install("another")
MIXED_EARS = "another-ears-mixed"


def _hearing_two_languages() -> Catalog:
    row = THE_CATALOG.model_dump(mode="json")
    row["heard"] = {f"stt/{acme.ACME}/{acme.EARS}": ["en", "es"]}
    row["multilingual"] = [f"stt/{acme.ACME}/{acme.EARS}"]
    return Catalog.model_validate(row)


def _with_other_ears() -> Catalog:
    row = _hearing_two_languages().model_dump(mode="json")
    row["heard"] |= {f"stt/{acme.ACME}/{WIDE_EARS}": ["ar", "en"], f"stt/{ANOTHER}/{MIXED_EARS}": ["ar", "en"]}
    row["multilingual"] += [f"stt/{ANOTHER}/{MIXED_EARS}"]
    row["ears"] = [{"vendor": acme.ACME, "model": WIDE_EARS}, {"vendor": ANOTHER, "model": MIXED_EARS}]
    return Catalog.model_validate(row)


def test_ears_that_do_not_hear_the_agents_language_are_warned_of_with_what_fixes_it() -> None:
    """Named ears say to take them out and what then runs; with none listed that hear it, to name some that do."""
    named = Declaration(slug="front-desk", language="ar-EG", stt=Model(vendor=acme.ACME, model=acme.EARS))
    warned = list_warnings(named, _with_other_ears(), ALL_OF_ACME)
    assert list(warned) == ["hears"]
    assert warned["hears"].startswith(f"{acme.ACME}/{acme.EARS} does not hear ar (it hears en, es)")
    assert warned["hears"].endswith(
        f"take the transcriber out of its settings and Pinecall runs {acme.ACME}/{WIDE_EARS}"
    )
    unnamed = list_warnings(Declaration(slug="front-desk", language="ar"), _hearing_two_languages(), ALL_OF_ACME)
    assert unnamed["hears"].endswith("no transcriber this runtime lists does: name one that does")


def test_ears_that_would_hear_every_language_and_have_no_key_are_said_with_how_to_bring_one() -> None:
    """Arabic and English run the ears that hear Arabic alone: the warning names the ones that mix them, and why not."""
    both = Declaration(slug="front-desk", language="ar, en")
    warned = list_warnings(both, _with_other_ears(), ALL_OF_ACME)
    assert warned["hears"].startswith(
        f"{acme.ACME}/{WIDE_EARS} hears one language a call, and this agent's callers speak ar, en: "
        f"{ANOTHER}/{MIXED_EARS} does, and this org cannot run it ({ANOTHER} has no key"
    )
    assert warned["hears"].endswith(f"pinecall providers add {ANOTHER}")
    keyed = Keyring(box={acme.ACME: "box-key"}, own={ANOTHER: "own-key"})
    assert list_warnings(both, _with_other_ears(), keyed) == {}


def test_a_language_the_ears_hear_or_one_nobody_set_is_warned_of_nothing() -> None:
    """Spanish is heard, two they mix are heard, no language is no promise, unlisted ears hear what they are told."""
    catalog = _hearing_two_languages()
    assert list_warnings(Declaration(slug="front-desk", language="es"), catalog, ALL_OF_ACME) == {}
    assert list_warnings(Declaration(slug="front-desk", language="es, en"), catalog, ALL_OF_ACME) == {}
    assert list_warnings(AGENT, catalog, ALL_OF_ACME) == {}
    assert list_warnings(Declaration(slug="front-desk", language="ar"), THE_CATALOG, ALL_OF_ACME) == {}
    assert list_warnings(Declaration(slug="front-desk", language="ar"), _with_other_ears(), ALL_OF_ACME) == {}


def test_a_voice_whose_model_does_not_speak_the_language_is_warned_of() -> None:
    """A voice the agent names on a model that speaks English alone, for callers who speak Arabic."""
    row = THE_CATALOG.model_dump(mode="json")
    row["spoken"] = {f"tts/{acme.ACME}/{acme.VOICE}": ["en"], f"tts/{acme.ACME}/acme-voice-wide": ["ar", "en"]}
    row["speakers"] = [{"vendor": acme.ACME, "model": "acme-voice-wide"}]
    catalog = Catalog.model_validate(row)
    named = Declaration(
        slug="front-desk", language="ar", voice=Voice(vendor=acme.ACME, voice_id="ana", model=acme.VOICE)
    )
    warned = list_warnings(named, catalog, ALL_OF_ACME)
    assert list(warned) == ["speaks"]
    assert warned["speaks"] == (
        f"{acme.ACME}/{acme.VOICE} does not speak ar (it speaks en): take the voice out of its settings and "
        f"Pinecall runs {acme.ACME}/acme-voice-wide"
    )
    assert list_warnings(Declaration(slug="front-desk", language="ar"), catalog, ALL_OF_ACME) == {}
    row["spoken"][f"tts/{acme.ACME}/{acme.VOICE}"] = [f"l{at:02}" for at in range(40)]
    many = list_warnings(named, Catalog.model_validate(row), ALL_OF_ACME)
    assert many["speaks"].startswith(f"{acme.ACME}/{acme.VOICE} does not speak ar (it speaks 40 languages): ")
