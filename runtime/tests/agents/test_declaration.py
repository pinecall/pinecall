"""What a class declares, held to what a call can run: a greeting is one of its two things; the opening asked for."""

import pytest

from runtime.agents.declaration import Declaration, Greeting, check_greeting, open_as_asked
from runtime.exceptions import ValidationError


def test_a_greeting_that_names_neither_verb_or_both_is_refused_at_declaration() -> None:
    with pytest.raises(ValidationError, match="one of two things"):
        check_greeting(Greeting())
    with pytest.raises(ValidationError, match="one of two things"):
        check_greeting(Greeting(say="a", reply="b"))
    check_greeting(Greeting(say="Hola"))


def test_a_call_placed_out_opens_on_its_own_words_or_on_what_it_is_for_and_any_other_on_the_agents() -> None:
    desk = Declaration(slug="desk", greeting=Greeting(say="Brightside Dental."))
    assert open_as_asked(desk, "Hi Ana, it is Brightside.", None).greeting == Greeting(say="Hi Ana, it is Brightside.")
    assert open_as_asked(desk, None, "Remind her of her visit.").greeting == Greeting(reply="Remind her of her visit.")
    assert open_as_asked(desk, "Hi Ana.", "Remind her of her visit.").greeting == Greeting(say="Hi Ana.")
    assert open_as_asked(desk, None, None) is desk
