"""Leaving: a drain then the socket closed, once, however many times it is asked."""

from pinecall.client import Client, Drained
from pinecall.serve._held import Held
from tests.fakes.gateway import KEY, FakeGateway


async def test_stopping_drains_closes_and_answers_the_same_drain_when_asked_again(
    gateway: FakeGateway,
) -> None:
    client = Client(gateway.url, KEY)
    client.agent("clinica")
    await client.connect()
    held = Held(client, [])
    first = await held.stop()
    assert first == Drained(1, 0, 0, 0)
    assert await held.stop() is first
    await held.closed()
    assert not client.connected
    assert len(gateway.commands_of("agent.drain")) == 1
