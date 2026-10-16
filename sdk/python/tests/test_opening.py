"""How a call opens and when the agent may end it, as a class writes them, read into the wire."""

import pytest

from pinecall import DeclarationRefused, improvise, words
from pinecall._opening import greeting_of, hangup_of


def test_an_opening_is_words_said_or_the_models_own_with_or_without_an_instruction() -> None:
    assert greeting_of("Clínica Norte, buenas.") == {"say": "Clínica Norte, buenas."}
    assert greeting_of(improvise) == {"reply": ""}
    assert greeting_of(improvise("Saludá por el nombre")) == {"reply": "Saludá por el nombre"}
    assert greeting_of(improvise("Saludá", interruptible=True)) == {
        "reply": "Saludá",
        "allow_interruptions": True,
    }
    assert greeting_of(words("Aviso legal…", interruptible=False)) == {
        "say": "Aviso legal…",
        "allow_interruptions": False,
    }
    with pytest.raises(DeclarationRefused, match="a greeting is the words"):
        greeting_of(42)


def test_hangup_is_when_in_words_or_true_for_whenever_the_model_judges() -> None:
    assert hangup_of("the caller says goodbye") == {"when": "the caller says goodbye"}
    assert hangup_of(True) == {"when": ""}  # noqa: FBT003 - the value a class writes
    with pytest.raises(DeclarationRefused, match="hangup is when the model may end the call"):
        hangup_of("")
