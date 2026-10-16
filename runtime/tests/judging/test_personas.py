"""A persona's model, vendor and voice are checked when it is written, never on the call that plays it."""

import pytest

from pinecall_runtime.exceptions import ValidationError
from pinecall_runtime.judging.service.personas import check_persona_models
from pinecall_runtime.providers.schemas import KeptVoice
from tests.conftest import configured
from tests.fakes import acme

LISTS_ANA = {"listed": {f"{acme.ACME}/es": (KeptVoice(id="acme-ana", name="Ana"),)}}


def test_a_vendor_this_box_lacks_is_refused_as_a_vendor_never_tried_as_a_model() -> None:
    with pytest.raises(ValidationError, match="no vendor named 'nonvendor'"):
        check_persona_models(configured(), None, "nonvendor", None)


def test_a_voice_the_vendors_catalog_does_not_list_is_refused_by_name() -> None:
    listing = configured().model_copy(update=LISTS_ANA)
    with pytest.raises(ValidationError, match="acme lists no voice acme-zzz"):
        check_persona_models(listing, None, acme.ACME, "acme-zzz")
    check_persona_models(listing, None, acme.ACME, "acme-ana")


def test_a_vendor_listing_no_voices_takes_the_id_as_given() -> None:
    check_persona_models(configured(), None, acme.ACME, "a-voice-of-its-own")


def test_a_model_on_a_vendor_nobody_installed_is_refused() -> None:
    with pytest.raises(ValidationError, match="no vendor named 'nonsense'"):
        check_persona_models(configured(), "nonsense/none", None, None)
