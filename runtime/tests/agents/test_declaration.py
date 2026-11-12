"""What a class declares, held to what a call can run: a greeting is one of its two things."""

import pytest

from runtime.agents.declaration import Greeting, check_greeting
from runtime.exceptions import ValidationError


def test_a_greeting_that_names_neither_verb_or_both_is_refused_at_declaration() -> None:
    with pytest.raises(ValidationError, match="one of two things"):
        check_greeting(Greeting())
    with pytest.raises(ValidationError, match="one of two things"):
        check_greeting(Greeting(say="a", reply="b"))
    check_greeting(Greeting(say="Hola"))
