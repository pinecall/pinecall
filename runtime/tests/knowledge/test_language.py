"""A base's language: said by its code or name, or counted from its function words, else `simple`."""

import pytest

from pinecall_runtime.exceptions import ValidationError
from pinecall_runtime.knowledge.service.language import detected, language_of

ENGLISH = "The agent answers the call and hands it to a person when the caller asks for one. It is written as a class."
SPANISH = "El agente atiende la llamada y la pasa a una persona cuando el que llama lo pide. Se escribe como una clase."
PORTUGUESE = "O agente atende a chamada e a passa para uma pessoa quando quem liga pede. É escrito como uma classe."
A_TABLE = "| Monday | 9 | 18 |\n| Tuesday | 9 | 18 |\n| Wednesday | 9 | 18 |"
# The suites' own Spanish fixtures (test_bases.py): two sentences, and still Spanish, not Portuguese.
PRICES = "# Precios\n\nUna limpieza cuesta 40 euros y dura media hora.\n"
HOURS = "# Horario\n\nAbrimos de lunes a viernes, de nueve a siete.\n"


@pytest.mark.parametrize(
    ("said", "language"), [("en", "english"), ("English", "english"), ("es", "spanish"), ("simple", "simple")]
)
def test_a_language_is_said_by_its_code_or_its_name(said: str, language: str) -> None:
    """`en` and `english` are the one configuration; case and spaces are forgiven."""
    assert language_of(said) == language


def test_a_language_nobody_said_is_none_and_one_that_is_not_one_is_refused() -> None:
    """None asks for detection; a word that is no configuration is refused naming the ones that are."""
    assert language_of(None) is None
    with pytest.raises(ValidationError, match="english, spanish"):
        language_of("klingon")


@pytest.mark.parametrize(("text", "language"), [(ENGLISH, "english"), (SPANISH, "spanish"), (PORTUGUESE, "portuguese")])
def test_the_function_words_say_the_language(text: str, language: str) -> None:
    """A paragraph in each language is told by its articles and prepositions alone."""
    assert detected([text]) == language


def test_a_text_with_no_function_words_is_simple() -> None:
    """A table of names and numbers says no language, and `simple` stems nothing."""
    assert detected([A_TABLE]) == "simple"
    assert detected([]) == "simple"


# The 2026-10-23 eval's table: its last row's `Y8` was read as the Spanish `y`, and the base as Spanish.
A_TABLE_OF_CODES = (
    "# Rates\n\n| code | zone | rate |\n|---|---|---|\n| A1 | N | 10 |\n| B2 | S | 12 |\n| C3 | E | 15 |\n"
    "| D4 | W | 18 |\n\n## Codes\n\n| id | tag |\n|---|---|\n| X9 | QQ |\n| Y8 | ZZ |\n| W7 | PP |\n"
)
A_TABLE_OF_LOTS = "# SKU\n\n| SKU | QTY | LOT |\n|---|---|---|\n| KX-100 | 40 | L7731 |\n| ZR-310 | 77 | L7733 |\n"


@pytest.mark.parametrize("table", [A_TABLE_OF_CODES, A_TABLE_OF_LOTS])
def test_the_letters_of_a_code_are_not_words(table: str) -> None:
    """`Y8`, `A1` and `L7731` are codes: a table of them says no language and is `simple`."""
    assert detected([table]) == "simple"


def test_a_code_among_prose_changes_nothing() -> None:
    """The words of the prose decide; a count or a code beside them is not one."""
    assert detected([f"{ENGLISH}\n\nSee Y8 and 2nd floor, lot L7731."]) == "english"


def test_the_files_are_counted_together() -> None:
    """A folder is one language: the words of every file are counted as one text."""
    assert detected([ENGLISH, ENGLISH, A_TABLE]) == "english"


def test_two_short_spanish_sentences_are_spanish_and_not_portuguese() -> None:
    """`de` and `a` are both languages' and count for neither; `y` is Spanish alone and decides."""
    assert detected([PRICES, HOURS]) == "spanish"
