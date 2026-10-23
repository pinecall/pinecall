"""The relay of a followed log: a message it cannot apply is said with its channel, and the next is delivered."""

import asyncio

import pytest

from pinecall_runtime.calls.relay import Relay, encoded
from pinecall_runtime.redis import LocalSignal
from pinecall_runtime.wire.base import Entry
from tests.conftest import until

CHANNEL = "log:call_1"


def an_entry(seq: int) -> Entry:
    """An entry another gateway wrote."""
    return Entry(seq=seq, ts=float(seq), call="call_1", agent="clinica-norte", type="custom", ephemeral=False, data={})


async def nothing_stored(_log: str, _after: int, _limit: int) -> list[Entry]:
    return []


async def at_zero(_log: str) -> int:
    return 0


# A message that raised ended the task that followed the log: its readers on this gateway heard nothing
# of what other gateways wrote to it for as long as they stayed, and nothing said so.
async def test_a_message_the_relay_cannot_read_or_deliver_is_said_and_the_next_is_delivered(
    caplog: pytest.LogCaptureFixture,
) -> None:
    signal = LocalSignal()
    delivered: list[int] = []

    def deliver(_channel: str, entry: Entry) -> None:
        if entry.seq == 1:
            raise RuntimeError("a reader broke")
        delivered.append(entry.seq)

    relay = Relay(signal, nothing_stored, at_zero, deliver, lambda _channel: None)
    await relay.follow(CHANNEL, ordered=False)
    try:
        signal.publish(CHANNEL, b"this is not a message")
        signal.publish(CHANNEL, encoded(an_entry(1), "another-gateway"))
        signal.publish(CHANNEL, encoded(an_entry(2), "another-gateway"))
        await until(lambda: delivered == [2])
        assert f"following a log failed on {CHANNEL}" in caplog.text
    finally:
        await asyncio.wait_for(relay.close(), 5)
