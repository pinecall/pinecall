"""The signal on Redis: its sender and its listener go on after what is not Redis's own error."""

import asyncio
import os
from collections.abc import AsyncIterator
from typing import Any, override
from uuid import uuid4

import pytest
from redis.asyncio import Redis
from redis.asyncio.client import Pipeline, PubSub

from runtime.redis import RedisSignal, new_gateway_id
from tests.conftest import needs_the_services, until

pytestmark = needs_the_services


class PipelinesOnceWrong(Redis):
    """The suite's Redis, whose first pipeline raises what is not Redis's error: a bug in what was queued."""

    pipelined = 0

    @override
    def pipeline(self, transaction: bool = True, shard_hint: Any = None) -> Pipeline:
        type(self).pipelined += 1
        if type(self).pipelined == 1:
            raise ValueError("a bug in what was queued")
        return super().pipeline(transaction, shard_hint)


class ListensOnceWrong(Redis):
    """The suite's Redis, whose first listening raises what is not Redis's error: a bug in what was heard."""

    listened = 0

    @override
    def pubsub(self, **kwargs: Any) -> PubSub:
        type(self).listened += 1
        if type(self).listened == 1:
            raise ValueError("a bug in what was heard")
        return super().pubsub(**kwargs)  # pyright: ignore[reportUnknownMemberType]


def a_signal(client: Redis, listener: Redis) -> RedisSignal:
    """A signal on these two connections, under a prefix of its own."""
    return RedisSignal(client, listener, gateway=new_gateway_id(), prefix=f"suite-{uuid4().hex[:8]}:")


def at_the_suites(kind: type[Redis]) -> Redis:
    """A connection of this kind to the suite's Redis."""
    connection: Redis = kind.from_url(os.environ["PINECALL_REDIS_URL"])  # pyright: ignore[reportUnknownMemberType]
    return connection


@pytest.fixture
async def sending_wrong() -> AsyncIterator[RedisSignal]:
    """A signal whose first pipeline raises; closed after."""
    PipelinesOnceWrong.pipelined = 0
    opened = a_signal(at_the_suites(PipelinesOnceWrong), at_the_suites(Redis))
    yield opened
    await opened.close()


@pytest.fixture
async def hearing_wrong() -> AsyncIterator[RedisSignal]:
    """A signal whose first listening raises; closed after."""
    ListensOnceWrong.listened = 0
    opened = a_signal(at_the_suites(Redis), at_the_suites(ListensOnceWrong))
    yield opened
    await opened.close()


# A pipeline that raised anything but a RedisError ended the sender, and nothing was published again
# by this gateway, with nothing but a silence to say so.
async def test_a_sender_that_met_an_error_that_is_not_redis_goes_on(sending_wrong: RedisSignal) -> None:
    signal = sending_wrong
    signal.start()
    await asyncio.wait_for(signal.wait_until_up(), 10)
    listener = await signal.subscribe("a-channel")
    signal.publish("a-channel", b"lost")
    await until(lambda: PipelinesOnceWrong.pipelined >= 1, 30)
    signal.publish("a-channel", b"heard")
    assert await asyncio.wait_for(anext(listener), 30) == b"heard"
    assert signal.dropped == 1


# A message that raised in the listener ended it: no gateway's word was heard again, and no listener
# was told to resume from the store, since the loop that tells them was the one that ended.
async def test_a_listener_that_met_an_error_that_is_not_redis_comes_back(hearing_wrong: RedisSignal) -> None:
    hearing_wrong.start()
    await asyncio.wait_for(hearing_wrong.wait_until_up(), 30)
    assert ListensOnceWrong.listened >= 2
