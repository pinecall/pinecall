"""A loop's item that raises is said with where it was, and the loop goes on; its cancellation is not swallowed."""

import asyncio
import logging

import pytest

from pinecall_runtime.kit.loops import survived


def test_what_an_item_raises_is_said_with_where_it_was_and_the_next_item_runs(caplog: pytest.LogCaptureFixture) -> None:
    done: list[str] = []
    for item in ("call_a", "call_b", "call_c"):
        with survived("sealing", item):
            if item == "call_b":
                raise ValueError("1 validation error for CallStarted")
            done.append(item)
    assert done == ["call_a", "call_c"]
    [said] = [record for record in caplog.records if record.levelno == logging.WARNING]
    assert said.getMessage() == "sealing failed on call_b"
    assert said.exc_info is not None and said.exc_info[0] is ValueError


def test_a_pass_with_no_item_to_name_is_said_without_one(caplog: pytest.LogCaptureFixture) -> None:
    with survived("the sweep"):
        raise RuntimeError("the database lagged")
    assert [record.getMessage() for record in caplog.records] == ["the sweep failed"]


def test_the_block_says_whether_it_failed_for_a_loop_that_keeps_the_names_of_what_did() -> None:
    refused: list[str] = []
    for org in ("a", "b"):
        with survived("admitting numbers", org) as admitting:
            if org == "a":
                raise OSError("the SFU refused")
        if admitting.failed:
            refused.append(org)
    assert refused == ["a"]


def test_what_the_loop_itself_ends_on_is_raised_again() -> None:
    with pytest.raises(OSError, match="gone"), survived("sending", "call_a", unless=(OSError, RuntimeError)):
        raise OSError("socket gone")


async def test_an_await_in_the_block_is_survived_too_and_a_cancellation_is_not() -> None:
    async def boom() -> None:
        raise OSError("the SFU did not answer")

    with survived("offering", "room_1"):
        await boom()
    waiting = asyncio.create_task(asyncio.sleep(10))
    waiting.cancel()
    with pytest.raises(asyncio.CancelledError), survived("offering", "room_2"):
        await waiting
