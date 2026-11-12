"""The overflow's one sentence: in the agent's language, or the operator's own for every call."""

from runtime.jobs.service.overflow import ALL_LINES_BUSY, sentence_in


# Until 2026-11 the sentence was Spanish for every call: a caller of an English agent whose fleet was
# full was told so in a language they had not been spoken to in.
def test_the_overflow_speaks_the_agents_language_and_english_where_it_has_no_sentence_in_it() -> None:
    assert sentence_in("en", None) == ALL_LINES_BUSY["en"]
    assert sentence_in("es-ES", None) == ALL_LINES_BUSY["es"]
    assert sentence_in("de", None) == ALL_LINES_BUSY["en"]
    assert sentence_in(None, None) == ALL_LINES_BUSY["en"]


def test_a_sentence_the_operator_named_is_said_to_every_call() -> None:
    assert sentence_in("es", "All our lines are busy.") == "All our lines are busy."
    assert sentence_in("es", "") == ALL_LINES_BUSY["es"]
