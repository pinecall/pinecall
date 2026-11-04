"""A vendor's failure read off a sealed log: which stage and vendor, whose key, how many errors."""

from typing import Any

from pinecall_runtime.alerts.service.vendors import failure_of
from pinecall_runtime.wire.base import Entry

GEMINI_504 = (
    "type='llm_error' timestamp=1793805400.7 label='livekit.plugins.google.llm.LLM' "
    "error=APIStatusError('gemini llm: server error', status_code=504, request_id='1db9d7713f68')\nmore"
)
SAID_NOTHING = "the model said nothing within 12s, so the caller was asked to say it again"


def entry(kind: str, data: dict[str, Any], *, call: str = "call_1", seq: int = 1) -> Entry:
    """One line of the call's log."""
    return Entry(seq=seq, ts=1.0, call=call, agent="front-desk", type=kind, ephemeral=False, data=data)


def test_a_component_error_names_its_vendor_its_stage_and_whose_key_it_ran_on() -> None:
    """A Gemini 504 on the LLM is google's failure as the model, on the org's own key when google was not lent."""
    log = [
        entry("turn.user", {"text": "Hello"}),
        entry("error", {"code": "component_failed", "message": GEMINI_504, "recoverable": True}, seq=2),
        entry("error", {"code": "llm_timeout", "message": SAID_NOTHING, "recoverable": True}, seq=3),
    ]
    failed = failure_of("call_1", log, lent=["deepgram"])
    assert failed is not None
    assert (failed.stage, failed.vendor, failed.code, failed.own_key, failed.errors) == (
        "llm",
        "google",
        "component_failed",
        True,
        2,
    )
    assert failed.message.startswith("type='llm_error'") and "\n" not in failed.message
    lent = failure_of("call_1", log, lent=["google/gemini-3.5-flash-lite", "deepgram"])
    assert lent is not None and lent.own_key is False


def test_a_model_that_said_nothing_is_the_llms_failure_with_no_vendor_named() -> None:
    """A timeout alone names no plugin: the stage is the model's and the vendor is unknown."""
    log = [entry("error", {"code": "llm_timeout", "message": SAID_NOTHING, "recoverable": True})]
    failed = failure_of("call_1", log, lent=[])
    assert failed is not None
    assert (failed.stage, failed.vendor, failed.own_key, failed.errors) == ("llm", "", False, 1)


def test_a_stage_that_switched_away_from_its_vendor_is_that_vendors_failure() -> None:
    """A vendor.switched with the vendor unavailable names the stage, the vendor and the model."""
    switched = {
        "stage": "tts",
        "vendor": "Gemini",
        "model": "gemini-3.8-flash-lite-tts",
        "available": False,
        "serving": "Deepgram",
        "serving_model": "aura-2-thalia-en",
    }
    failed = failure_of("call_1", [entry("vendor.switched", switched)], lent=[])
    assert failed is not None
    assert (failed.stage, failed.vendor, failed.model, failed.code) == (
        "tts",
        "Gemini",
        "gemini-3.8-flash-lite-tts",
        "vendor.switched",
    )
    assert failed.message == "the stage switched to Deepgram"
    came_back = failure_of("call_1", [entry("vendor.switched", {**switched, "available": True})], lent=[])
    assert came_back is None


def test_a_log_with_no_vendor_error_and_another_calls_errors_fail_nothing() -> None:
    """A refused tool is not a vendor's failure, and another call's entries are not this call's."""
    log = [
        entry("error", {"code": "refused", "message": "no such tool", "recoverable": True}),
        entry("error", {"code": "component_failed", "message": GEMINI_504, "recoverable": True}, call="call_2", seq=2),
    ]
    assert failure_of("call_1", log, lent=[]) is None
