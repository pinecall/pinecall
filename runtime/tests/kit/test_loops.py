"""A loop's item that raises is said with where it was, and the loop goes on; its cancellation is not swallowed."""

import asyncio
import logging

import pytest

from runtime.kit.loops import Loops, loop, survive
from tests.conftest import until


def test_what_an_item_raises_is_said_with_where_it_was_and_the_next_item_runs(caplog: pytest.LogCaptureFixture) -> None:
    done: list[str] = []
    for item in ("call_a", "call_b", "call_c"):
        with survive("sealing", item):
            if item == "call_b":
                raise ValueError("1 validation error for CallStarted")
            done.append(item)
    assert done == ["call_a", "call_c"]
    [said] = [record for record in caplog.records if record.levelno == logging.WARNING]
    assert said.getMessage() == "sealing failed on call_b"
    assert said.exc_info is not None and said.exc_info[0] is ValueError


def test_a_pass_with_no_item_to_name_is_said_without_one(caplog: pytest.LogCaptureFixture) -> None:
    with survive("the sweep"):
        raise RuntimeError("the database lagged")
    assert [record.getMessage() for record in caplog.records] == ["the sweep failed"]


def test_the_block_says_whether_it_failed_for_a_loop_that_keeps_the_names_of_what_did() -> None:
    refused: list[str] = []
    for org in ("a", "b"):
        with survive("admitting numbers", org) as admitting:
            if org == "a":
                raise OSError("the SFU refused")
        if admitting.failed:
            refused.append(org)
    assert refused == ["a"]


def test_what_the_loop_itself_ends_on_is_raised_again() -> None:
    with pytest.raises(OSError, match="gone"), survive("sending", "call_a", unless=(OSError, RuntimeError)):
        raise OSError("socket gone")


async def test_an_await_in_the_block_is_survived_too_and_a_cancellation_is_not() -> None:
    async def boom() -> None:
        raise OSError("the SFU did not answer")

    with survive("offering", "room_1"):
        await boom()
    waiting = asyncio.create_task(asyncio.sleep(10))
    waiting.cancel()
    with pytest.raises(asyncio.CancelledError), survive("offering", "room_2"):
        await waiting


# A loop once caught four classes of error, and a pydantic one out of something it could not read
# ended it for good. The pass after a failure waits longer, which is why this takes two seconds.
async def test_a_pass_that_raises_anything_is_counted_and_the_loop_goes_on() -> None:
    passes: list[int] = []

    @loop("a-loop", every_s=0.01)
    async def fail_the_first_time(seen: list[int]) -> None:
        seen.append(len(seen))
        if len(seen) == 1:
            raise ValueError("1 validation error for Dispatch\nagent\n  Field required")

    running = Loops()
    running.start(fail_the_first_time.bind(passes))
    try:
        await until(lambda: len(passes) >= 3)
        [beat] = running.beats()
        assert (beat.name, beat.alive, beat.failures) == ("a-loop", True, 1)
    finally:
        await running.stop()


async def test_a_name_runs_once() -> None:
    @loop("a-loop", every_s=60.0)
    async def idle() -> None:
        return None

    running = Loops()
    running.start(idle.bind())
    try:
        with pytest.raises(ValueError, match="a loop named a-loop runs already"):
            running.start(idle.bind())
    finally:
        await running.stop()
