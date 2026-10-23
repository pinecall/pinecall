"""The signal on Redis: its sender and its listener go on after what is not Redis's own error."""

import asyncio
import os
from collections.abc import AsyncIterator, Callable
from typing import cast
from uuid import uuid4

import pytest

from pinecall_runtime.redis import RedisSignal
from tests.conftest import needs_the_services, until

pytestmark = needs_the_services


@pytest.fixture
async def signal() -> AsyncIterator[RedisSignal]:
    """A signal on the suite's Redis under a prefix of its own, closed after."""
    opened = RedisSignal(os.environ["PINECALL_REDIS_URL"], prefix=f"suite-{uuid4().hex[:8]}:")
    yield opened
    await opened.close()


# A pipeline that raised anything but a RedisError ended the sender, and nothing was published again
# by this gateway, with nothing but a silence to say so.
async def test_a_sender_that_met_an_error_that_is_not_redis_goes_on(
    monkeypatch: pytest.MonkeyPatch, signal: RedisSignal
) -> None:
    signal.start()
    await asyncio.wait_for(signal.connected(), 10)
    listener = await signal.subscribe("a-channel")
    pipelined = 0
    real = cast(Callable[..., object], signal._client.pipeline)

    def pipeline(*args: object, **kwargs: object) -> object:
        nonlocal pipelined
        pipelined += 1
        if pipelined == 1:
            raise ValueError("a bug in what was queued")
        return real(*args, **kwargs)

    monkeypatch.setattr(signal._client, "pipeline", pipeline)
    signal.publish("a-channel", b"lost")
    await until(lambda: pipelined >= 1, 30)
    signal.publish("a-channel", b"heard")
    assert await asyncio.wait_for(anext(listener), 30) == b"heard"
    assert signal.dropped == 1


# A message that raised in the listener ended it: no gateway's word was heard again, and no listener
# was told to resume from the store, since the loop that tells them was the one that ended.
async def test_a_listener_that_met_an_error_that_is_not_redis_comes_back(
    monkeypatch: pytest.MonkeyPatch, signal: RedisSignal
) -> None:
    heard = signal._heard
    tries = 0

    async def flaky() -> None:
        nonlocal tries
        tries += 1
        if tries == 1:
            raise ValueError("a bug in what was heard")
        await heard()

    monkeypatch.setattr(signal, "_heard", flaky)
    signal.start()
    await asyncio.wait_for(signal.connected(), 30)
    assert tries >= 2
