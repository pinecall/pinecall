"""The org's word on the sentences a call says first: its own disclosure, none, or the platform's handed in."""

from runtime.compliance.service.policy import Policy

CALLING_FOR = "Le habla un asistente automático en nombre de {org}."
MAY_BE_RECORDED = "Esta llamada puede ser grabada."


def test_an_org_that_wrote_nothing_says_the_platforms_sentences_with_its_name_in_them() -> None:
    assert Policy().disclosure_for("Al Noor", CALLING_FOR) == "Le habla un asistente automático en nombre de Al Noor."
    assert Policy().notice_in(MAY_BE_RECORDED) == MAY_BE_RECORDED


def test_an_org_that_wrote_its_own_disclosure_says_it_and_one_that_wrote_none_says_nothing() -> None:
    own = Policy(disclosure="  Hola, soy el asistente de Al Noor.  ")
    assert own.disclosure_for("Al Noor", CALLING_FOR) == "Hola, soy el asistente de Al Noor."
    assert Policy(disclosure="").disclosure_for("Al Noor", CALLING_FOR) is None
    assert Policy(recording_notice=False).notice_in(MAY_BE_RECORDED) is None
