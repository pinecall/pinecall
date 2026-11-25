"""What the gateway answers a request it refuses: its status, its sentence, and when to come back."""

import json
from typing import cast

from sqlalchemy.exc import TimeoutError as PoolTimeout
from starlette.requests import Request

from runtime.app import answer_busy, answer_refusal
from runtime.exceptions import ServiceUnavailable

A_REQUEST = cast("Request", None)
A_FULL_POOL = "QueuePool limit of size 8 overflow 0 reached, connection timed out, timeout 2.00"


# 2026-11-25: thirty simulated calls on one gateway took its eight connections for two seconds, and the
# `pinecall simulate` that followed twenty of them ended on the first `503` its read of a call met. A
# busy database is back in a moment, and the answer says so: a reader asks again on that word.
async def test_a_request_the_pool_had_no_connection_for_is_told_when_to_ask_again() -> None:
    answered = await answer_busy(A_REQUEST, PoolTimeout(A_FULL_POOL))
    assert answered.status_code == 503
    assert answered.headers["retry-after"] == "1"
    assert json.loads(bytes(answered.body))["detail"].startswith("the database is busy")


# A vendor nobody keyed is a `503` too, and asked again it answers the same until somebody adds the key.
async def test_what_the_box_lacks_until_somebody_acts_names_no_time_to_come_back() -> None:
    answered = await answer_refusal(A_REQUEST, ServiceUnavailable("no key for elevenlabs in this env"))
    assert answered.status_code == 503
    assert "retry-after" not in answered.headers
