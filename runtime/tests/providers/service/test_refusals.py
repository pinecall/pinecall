"""A vendor's refusal read in its own words, never the SDK's repr of its body."""

import pytest
from livekit.agents import APIConnectionError, APIStatusError, llm, stt, tts

from runtime.enums import Stage
from runtime.providers.service import refusals
from runtime.providers.service.refusals import say_failure, sentence_of, stage_named_in, vendor_named_in

AN_SDKS_MESSAGE = "Error code: 401 - {'message': 'Wrong API Key', 'type': 'invalid_request_error'}"


def test_the_bodys_message_is_the_vendors_words() -> None:
    refused = APIStatusError(AN_SDKS_MESSAGE, status_code=401, body={"message": "Wrong API Key"})
    assert sentence_of(refused) == "Wrong API Key"


def test_a_message_under_error_is_found_there() -> None:
    refused = APIStatusError(AN_SDKS_MESSAGE, status_code=401, body={"error": {"message": "invalid x-api-key"}})
    assert sentence_of(refused) == "invalid x-api-key"


def test_with_no_body_to_read_the_message_is_what_there_is() -> None:
    assert sentence_of(APIConnectionError("no answer")) == "no answer"
    assert sentence_of(APIStatusError("teapot", status_code=418, body="not json")) == "teapot"


# ── a component of a live call that failed ──

NO_CREDIT = "Your credit balance is too low to access the Anthropic API."


def test_a_failed_component_is_said_in_a_sentence_with_livekits_own_account_under_it() -> None:
    """The reason first, in the vendor's words after the colon; then what livekit said, where the plugin is read."""
    body = {"type": "error", "error": {"type": "invalid_request_error", "message": NO_CREDIT}}
    refused = APIStatusError(f"Error code: 400 - {body}", status_code=400, body=body)
    failed = llm.LLMError(timestamp=1.0, label="livekit.plugins.anthropic.llm.LLM", error=refused, recoverable=False)
    reason, _, livekits_own = say_failure(failed).partition("\n")
    assert reason == f"anthropic refused this call's model: {NO_CREDIT}"
    assert livekits_own == str(failed)
    assert (vendor_named_in(livekits_own), stage_named_in(livekits_own)) == ("anthropic", Stage.llm)


def test_a_vendor_failing_on_its_side_and_one_that_does_not_answer_are_said_as_theirs() -> None:
    """A 5xx is the vendor's own failure, a connection that broke its silence: neither is a refusal of the call."""
    down = APIStatusError("upstream", status_code=503, body={"message": "service unavailable"})
    ears = stt.STTError(timestamp=1.0, label="livekit.plugins.deepgram.stt.STT", error=down, recoverable=True)
    assert say_failure(ears).split("\n")[0] == "deepgram failed on its side (503): service unavailable"
    silent = tts.TTSError(
        timestamp=1.0,
        label="livekit.plugins.cartesia.tts.TTS",
        error=APIConnectionError("connection reset"),
        recoverable=True,
    )
    assert say_failure(silent).split("\n")[0] == "cartesia did not answer: connection reset"


def test_a_component_that_names_no_plugin_and_an_error_that_is_no_vendors_are_still_a_sentence() -> None:
    """With no plugin in the label nobody is named; an error that is not the vendor's answer is said as it reads."""
    broke = llm.LLMError(timestamp=1.0, label="acme", error=RuntimeError("the stream ended early"), recoverable=False)
    assert say_failure(broke).split("\n")[0] == "the vendor failed this call: the stream ended early"
    assert stage_named_in(str(broke)) is None


@pytest.mark.parametrize(
    ("status", "body", "message"),
    [
        (429, {"error": {"message": "You have no credits remaining.", "code": "insufficient_quota"}}, "quota"),
        (
            400,
            {"type": "error", "error": {"type": "invalid_request_error", "message": "Your credit balance is too low"}},
            "x",
        ),
        (403, None, "personal-team-blocked:spending-limit reached for this team"),
    ],
)
def test_a_vendor_that_will_not_serve_an_unpaid_account_is_told_apart(status: int, body: object, message: str) -> None:
    assert refusals.is_unpaid(APIStatusError(message, status_code=status, body=body))


# 2026-11-26: xAI answered the realtime handshake of an account out of credit with a bare 402, and its
# plugin raised "client connection error": fourteen calls were said not to have been answered.
class _HandshakeRefused(Exception):
    def __init__(self, status: int) -> None:
        super().__init__(f"{status}, message='Invalid response status'")
        self.status = status


def _refused_at_the_handshake(status: int) -> APIConnectionError:
    silent = APIConnectionError("xAI Realtime API client connection error")
    silent.__cause__ = _HandshakeRefused(status)
    return silent


def test_a_connection_a_vendor_refused_for_payment_is_an_unpaid_account_and_is_said_as_a_refusal() -> None:
    refused = _refused_at_the_handshake(402)
    assert refusals.status_behind(refused) == 402
    assert refusals.is_unpaid(refused)
    voice = llm.RealtimeModelError(
        timestamp=1.0,
        label="livekit.plugins.xai.realtime.realtime_model.RealtimeModel",
        error=refused,
        recoverable=True,
    )
    first = say_failure(voice).split("\n")[0]
    assert first == "xai refused this call: it answered the connection 402 Payment Required"


def test_a_connection_that_only_broke_names_no_status_and_is_the_vendors_silence() -> None:
    broke = APIConnectionError("connection reset")
    assert refusals.status_behind(broke) is None
    assert not refusals.is_unpaid(broke)
    assert refusals.status_behind(_refused_at_the_handshake(503)) == 503
    assert not refusals.is_unpaid(_refused_at_the_handshake(503))


def test_a_rate_limit_is_not_an_unpaid_account() -> None:
    limited = APIStatusError("Rate limit reached", status_code=429, body={"error": {"code": "rate_limit_exceeded"}})
    assert not refusals.is_unpaid(limited)
