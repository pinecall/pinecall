"""A bound call's pump: an entry it cannot send is said and skipped, a socket that is gone ends it."""

from collections.abc import AsyncIterator
from typing import cast

import pytest

from pinecall_runtime.calls.logs import Log
from pinecall_runtime.calls.service.pump import pump
from pinecall_runtime.wire.base import Entry


def an_entry(seq: int) -> Entry:
    """The call's entry at this seq."""
    return Entry(seq=seq, ts=float(seq), call="call_1", agent="clinica-norte", type="custom", ephemeral=False, data={})


class Reading:
    """A call's log as the pump reads it: three entries, one of which may not be opened."""

    call = "call_1"

    def __init__(self, unopenable: int | None) -> None:
        """The seq the store cannot open, if any."""
        self.unopenable = unopenable

    async def stream(self, *, after: int) -> AsyncIterator[Entry]:
        """The call's entries above the cursor."""
        for seq in (1, 2, 3):
            if seq > after:
                yield an_entry(seq)

    async def opened(self, entry: Entry) -> Entry:
        """The entry as its writer wrote it, but for the one the store cannot open."""
        if entry.seq == self.unopenable:
            raise ValueError(f"the sealed values of seq {entry.seq} could not be opened")
        return entry


# A pump that ended on an entry it could not open left the app deaf to its call: its tool calls
# unanswered to their deadline, with nothing said of why.
async def test_an_entry_the_pump_cannot_send_is_said_with_its_call_and_the_next_is_sent(
    caplog: pytest.LogCaptureFixture,
) -> None:
    sent: list[int] = []

    async def send(entry: Entry) -> None:
        sent.append(entry.seq)

    await pump(cast(Log, Reading(unopenable=2)), 0, send, [])
    assert sent == [1, 3]
    assert "sending an entry down its call's socket failed on call_1 seq 2" in caplog.text


async def test_a_socket_that_is_gone_ends_the_pump_and_does_not_skip_its_entries() -> None:
    sent: list[int] = []

    async def send(entry: Entry) -> None:
        if entry.seq == 3:
            raise OSError("the socket closed")
        sent.append(entry.seq)

    await pump(cast(Log, Reading(unopenable=None)), 0, send, [])
    assert sent == [1, 2]
