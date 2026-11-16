"""A vendor's refusal read in its own words, never the SDK's repr of its body."""

from livekit.agents import APIConnectionError, APIStatusError, llm, stt, tts

from runtime.enums import Stage
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
