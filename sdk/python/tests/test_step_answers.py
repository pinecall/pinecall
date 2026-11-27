"""What a flow's steps came to: each answer as the flow reads it, and an extraction refused."""

from pinecall import Called, ExtractRefused, PinecallError, Templated, Texted


def test_each_steps_answer_says_what_it_came_to_and_nothing_else_by_default() -> None:
    assert Called(answered=True, call="call_7").call == "call_7"
    assert Texted(sent=False, refused="Forbidden").refused == "Forbidden"
    assert Texted(sent=True).from_ is None
    assert Templated(sent=True).simulated is False


def test_an_extraction_refused_is_a_pinecall_error_naming_what_refused_it() -> None:
    refused = ExtractRefused("Forbidden", "google is not lent to the org")
    assert isinstance(refused, PinecallError)
    assert (refused.refused, str(refused)) == ("Forbidden", "google is not lent to the org")
