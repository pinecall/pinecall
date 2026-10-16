"""A vendor's refusal read in its own words, never the SDK's repr of its body."""

from livekit.agents import APIConnectionError, APIStatusError

from pinecall_runtime.providers.service.plugins import words_of

AN_SDKS_MESSAGE = "Error code: 401 - {'message': 'Wrong API Key', 'type': 'invalid_request_error'}"


def test_the_bodys_message_is_the_vendors_words() -> None:
    refused = APIStatusError(AN_SDKS_MESSAGE, status_code=401, body={"message": "Wrong API Key"})
    assert words_of(refused) == "Wrong API Key"


def test_a_message_under_error_is_found_there() -> None:
    refused = APIStatusError(AN_SDKS_MESSAGE, status_code=401, body={"error": {"message": "invalid x-api-key"}})
    assert words_of(refused) == "invalid x-api-key"


def test_with_no_body_to_read_the_message_is_what_there_is() -> None:
    assert words_of(APIConnectionError("no answer")) == "no answer"
    assert words_of(APIStatusError("teapot", status_code=418, body="not json")) == "teapot"
