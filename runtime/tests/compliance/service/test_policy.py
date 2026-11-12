"""The sentences the platform says first, in the agent's language, and in English for any other."""

import pytest

from runtime.compliance.service.policy import CALLING_FOR, MAY_BE_RECORDED, Policy


@pytest.mark.parametrize(
    ("language", "notice"),
    [
        ("en", "This call may be recorded."),
        ("ar", "قد يتم تسجيل هذه المكالمة."),
        ("ar-AE", "قد يتم تسجيل هذه المكالمة."),
        ("es_MX", "Esta llamada puede ser grabada."),
        ("ja", "This call may be recorded."),
        (None, "This call may be recorded."),
    ],
)
def test_the_recording_notice_is_said_in_the_agents_language_and_in_english_for_any_other(
    language: str | None, notice: str
) -> None:
    assert Policy().notice_in(language) == notice


def test_the_platforms_disclosure_names_the_org_in_the_agents_language() -> None:
    assert Policy().disclosure_for("Al Noor", "ar") == "هذا مساعد آلي يتصل بالنيابة عن Al Noor."
    english = "This is an automated assistant calling on behalf of Al Noor."
    assert Policy().disclosure_for("Al Noor", "ja") == english


def test_every_language_with_a_notice_has_a_disclosure_too() -> None:
    assert set(MAY_BE_RECORDED) == set(CALLING_FOR)


def test_an_org_that_wrote_its_own_disclosure_says_it_and_one_that_wrote_none_says_nothing() -> None:
    assert Policy(disclosure="  Hola, soy el asistente de Al Noor.  ").disclosure_for("Al Noor", "es") == (
        "Hola, soy el asistente de Al Noor."
    )
    assert Policy(disclosure="").disclosure_for("Al Noor", "es") is None
    assert Policy(recording_notice=False).notice_in("es") is None
