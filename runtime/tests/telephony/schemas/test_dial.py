"""A dial's body: what its call opens with rides the room's dispatch, a visit and a reason, never a file."""

import pytest
from pydantic import ValidationError as PydanticValidationError

from runtime.telephony.schemas.dial import OPENING_BYTES, DialRequest


def test_a_dial_carries_what_its_call_opens_with_and_refuses_a_document() -> None:
    asked = DialRequest.model_validate({"to": "+14155550142", "state": {"visit": "v-812"}, "metadata": {"flow": "r-1"}})
    assert (asked.state, asked.metadata) == ({"visit": "v-812"}, {"flow": "r-1"})
    assert DialRequest.model_validate({"to": "+14155550142"}).state == {}
    with pytest.raises(PydanticValidationError, match="bytes of JSON at most"):
        DialRequest.model_validate({"to": "+14155550142", "state": {"notes": "x" * OPENING_BYTES}})
