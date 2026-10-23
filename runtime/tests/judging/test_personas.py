"""A persona's model, vendor and voice are checked when it is written, never on the call that plays it."""

import pytest

from pinecall_runtime.exceptions import Forbidden, ServiceUnavailable, ValidationError
from pinecall_runtime.judging.service.personas import check_persona_keys, check_persona_models
from pinecall_runtime.providers.schemas import KeptVoice
from pinecall_runtime.providers.service import Keyring
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


# ── and its key: a vendor nobody keyed is refused as its run would refuse it ──

THE_BOX = Keyring(box={acme.ACME: "acme-key"})


def test_a_model_on_a_vendor_nobody_keyed_is_refused_with_the_sentence_its_run_gives() -> None:
    with pytest.raises(ServiceUnavailable, match="openai has no key: the org brought none and the box holds none"):
        check_persona_keys(configured(), THE_BOX, "openai/gpt-5.4-mini", None)


def test_a_voices_vendor_nobody_keyed_is_refused_the_same_way() -> None:
    with pytest.raises(ServiceUnavailable, match="openai has no key"):
        check_persona_keys(configured(), THE_BOX, None, "openai")


def test_a_vendor_the_org_keyed_or_the_box_lends_is_taken_and_a_persona_that_names_none_is_not_asked() -> None:
    check_persona_keys(configured(), THE_BOX, f"{acme.ACME}/{acme.MODEL}", acme.ACME)
    check_persona_keys(configured(), Keyring(own={"openai": "the-orgs"}), "openai/gpt-5.4-mini", None)
    check_persona_keys(configured(), Keyring(), None, None)


def test_a_vendor_the_box_holds_a_key_for_and_does_not_lend_the_org_is_refused_naming_what_it_may_run() -> None:
    nothing_lent = Keyring(box={acme.ACME: "acme-key"}, lends=frozenset())
    with pytest.raises(Forbidden, match="not lent to this org"):
        check_persona_keys(configured(), nothing_lent, f"{acme.ACME}/{acme.MODEL}", None)
