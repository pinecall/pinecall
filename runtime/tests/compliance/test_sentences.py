"""The sentences the platform says first, in the agent's language, and in English for any other."""

import pytest

from pinecall_runtime.compliance import service as compliance
from pinecall_runtime.compliance.schemas import OrgPolicy


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
    assert compliance.notice_of(OrgPolicy(), language) == notice


def test_the_platforms_disclosure_names_the_org_in_the_agents_language() -> None:
    assert compliance.disclosure_of(OrgPolicy(), "Al Noor", "ar") == "هذا مساعد آلي يتصل بالنيابة عن Al Noor."
    english = "This is an automated assistant calling on behalf of Al Noor."
    assert compliance.disclosure_of(OrgPolicy(), "Al Noor", "ja") == english


def test_every_language_with_a_notice_has_a_disclosure_too() -> None:
    assert set(compliance.MAY_BE_RECORDED) == set(compliance.CALLING_FOR)
