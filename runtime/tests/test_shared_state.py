"""A share's two tickers, its beat and its listener, go on after a message or a beat that raised."""

import asyncio
import contextlib
import time
from collections.abc import AsyncIterator

import pytest
from pydantic import TypeAdapter

from runtime.shared_state import Heard, SharedState
from runtime.signal import LocalSignal
from tests.conftest import until

CHANNEL = "a-share"
AN_INTEGER = TypeAdapter(int)


def a_share(signal: LocalSignal, mine: int) -> SharedState[int]:
    """A share of one integer, told fast."""
    return SharedState(
        signal, CHANNEL, load=AN_INTEGER.validate_python, dump=int, empty=mine, on_change=lambda: None, every_s=0.01
    )


@pytest.fixture
async def signal() -> AsyncIterator[LocalSignal]:
    """The in-process signal two gateways' shares are told on."""
    yield LocalSignal()


# A share another gateway says that this one cannot read (a version that said more, a bug) was one
# exception out of the listener's loop, and this gateway heard no other for the rest of its life.
async def test_a_share_that_cannot_be_read_is_said_and_the_next_is_heard(signal: LocalSignal) -> None:
    mine, other = a_share(signal, 0), a_share(signal, 7)
    await mine.start()
    # The listener is there once a message has somebody to hear it; neither of these can be read.
    while await signal.publish_now(CHANNEL, b"this is not a share") == 0:
        await asyncio.sleep(0.01)
    signal.publish(CHANNEL, b'{"sender":"a-gateway","share":"not an integer"}')
    await other.start()
    try:
        await until(lambda: other.id in mine.theirs)
        assert mine.theirs[other.id].share == 7
    finally:
        await other.close()
        await mine.close()


async def test_a_beat_that_cannot_say_its_share_goes_on_to_the_next(signal: LocalSignal) -> None:
    told = 0

    def gathered() -> int:
        nonlocal told
        told += 1
        if told == 1:
            raise ValueError("the share could not be gathered")
        return told

    mine = a_share(signal, 0)
    mine.gathered = gathered
    await mine.start()
    try:
        await until(lambda: told >= 3)
    finally:
        await mine.close()


async def test_a_change_the_silence_of_a_gateway_makes_that_raises_does_not_end_the_beat(signal: LocalSignal) -> None:
    changes = 0

    def changed() -> None:
        nonlocal changes
        changes += 1
        if changes == 1:
            raise RuntimeError("the merge broke")

    mine = SharedState(
        signal,
        CHANNEL,
        load=AN_INTEGER.validate_python,
        dump=int,
        empty=0,
        on_change=changed,
        every_s=0.01,
        silent_after_s=0.0,
    )
    await mine.start()
    try:
        mine.theirs["a-gateway-that-left"] = Heard(1, time.monotonic() - 5)
        await until(lambda: changes >= 1)
        mine.theirs["another-that-left"] = Heard(2, time.monotonic() - 5)
        await until(lambda: changes >= 2)
        assert mine.theirs == {}
    finally:
        with contextlib.suppress(asyncio.CancelledError):
            await mine.close()
