"""A share's two tickers, its beat and its listener, go on after a message or a beat that raised."""

import asyncio
import contextlib
import time
from collections.abc import AsyncIterator

import pytest
from pydantic import TypeAdapter

from pinecall_runtime.kit import shared_state
from pinecall_runtime.kit.shared_state import Heard, SharedState
from pinecall_runtime.redis import LocalSignal
from tests.conftest import until

CHANNEL = "a-share"


def a_share(signal: LocalSignal, mine: int) -> SharedState[int]:
    """A share of one integer, told fast."""
    state = SharedState(signal, CHANNEL, TypeAdapter(int), mine, lambda: None)
    state.every_s = 0.01
    return state


@pytest.fixture
async def signal() -> AsyncIterator[LocalSignal]:
    """The in-process signal two gateways' shares are told on."""
    yield LocalSignal()


# A share another gateway says that this one cannot read (a version that said more, a bug) was one
# exception out of the listener's loop, and this gateway heard no other for the rest of its life.
async def test_a_share_that_cannot_be_read_is_said_and_the_next_is_heard(signal: LocalSignal) -> None:
    mine, other = a_share(signal, 0), a_share(signal, 7)
    await mine.start()
    await until(lambda: bool(signal._listening.get(CHANNEL)))
    signal.publish(CHANNEL, b"this is not a share")
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


async def test_a_change_the_silence_of_a_gateway_makes_that_raises_does_not_end_the_beat(
    monkeypatch: pytest.MonkeyPatch, signal: LocalSignal
) -> None:
    monkeypatch.setattr(shared_state, "SILENT_AT_MOST_S", 0.0)
    changes = 0

    def changed() -> None:
        nonlocal changes
        changes += 1
        if changes == 1:
            raise RuntimeError("the merge broke")

    mine = SharedState(signal, CHANNEL, TypeAdapter(int), 0, changed)
    mine.every_s = 0.01
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
