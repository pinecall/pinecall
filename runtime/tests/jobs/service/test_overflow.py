"""The overflow's one sentence: in the agent's language, a call back promised only where one is asked."""

from runtime.jobs.service.overflow import ALL_LINES_BUSY, WILL_CALL_BACK, sentence_in


# Until 2026-11 the sentence was Spanish for every call: a caller of an English agent whose fleet was
# full was told so in a language they had not been spoken to in.
def test_the_overflow_speaks_the_agents_language_and_english_where_it_has_no_sentence_in_it() -> None:
    assert sentence_in("en", None, calls_back=True) == WILL_CALL_BACK["en"]
    assert sentence_in("es-ES", None, calls_back=True) == WILL_CALL_BACK["es"]
    assert sentence_in("de", None, calls_back=True) == WILL_CALL_BACK["en"]
    assert sentence_in(None, None, calls_back=True) == WILL_CALL_BACK["en"]


# A visitor of a page has no number: "we have noted your number and will call you back" was said to them too.
def test_a_call_back_is_promised_only_to_a_caller_it_is_asked_for() -> None:
    assert "call you back" in sentence_in("en", None, calls_back=True)
    assert sentence_in("en", None, calls_back=False) == ALL_LINES_BUSY["en"]
    assert "call you back" not in sentence_in("en", None, calls_back=False)
    assert "devolveremos" not in sentence_in("es", None, calls_back=False)


def test_a_sentence_the_operator_named_is_said_to_every_call() -> None:
    assert sentence_in("es", "All our lines are busy.", calls_back=True) == "All our lines are busy."
    assert sentence_in("es", "", calls_back=False) == ALL_LINES_BUSY["es"]
