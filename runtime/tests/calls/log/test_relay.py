"""The relay of a followed log: a message it cannot apply is said with its channel, and the next is delivered."""

import asyncio

import pytest

from runtime.calls.log.fanout import EVERYTHING, Subscription
from runtime.calls.log.relay import Relay, encode
from runtime.calls.log.store import Store
from runtime.signal import LocalSignal
from runtime.wire.base import Entry
from tests.conftest import needs_the_database, until

# A feed's channel: handed on as it comes, with no log to read back.
CHANNEL = "feed:clinica:sandbox"


def an_entry(seq: int) -> Entry:
    """An entry another gateway wrote."""
    return Entry(seq=seq, ts=float(seq), call="call_1", agent="clinica-norte", type="custom", ephemeral=False, data={})


class Breaking:
    """A hearer of the channel whose first entry breaks it."""

    def __init__(self) -> None:
        self.heard: list[int] = []

    def publish(self, entry: Entry) -> None:
        """Take the entry, or break on the first."""
        if entry.seq == 1:
            raise RuntimeError("a reader broke")
        self.heard.append(entry.seq)

    def drop(self) -> None:
        """The channel was lost."""


# A message that raised ended the task that followed the log: its readers on this gateway heard nothing
# of what other gateways wrote to it for as long as they stayed, and nothing said so.
@needs_the_database
async def test_a_message_the_relay_cannot_read_or_deliver_is_said_and_the_next_is_delivered(
    store: Store, caplog: pytest.LogCaptureFixture
) -> None:
    signal = LocalSignal()
    hearer = Breaking()
    relay = Relay(signal, store)
    await relay.follow_feed(CHANNEL, hearer, Subscription(EVERYTHING, lambda _reader: None))
    try:
        signal.publish(CHANNEL, b"this is not a message")
        signal.publish(CHANNEL, encode(an_entry(1), "another-gateway"))
        signal.publish(CHANNEL, encode(an_entry(2), "another-gateway"))
        await until(lambda: hearer.heard == [2])
        assert f"following a log failed on {CHANNEL}" in caplog.text
    finally:
        await asyncio.wait_for(relay.close(), 5)
