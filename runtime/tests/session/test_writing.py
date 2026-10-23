"""A call's writer after it closed: a line written then is refused at once, and the journal names it."""

import logging

import pytest

from pinecall_runtime.exceptions import ServiceUnavailable
from pinecall_runtime.session.writing import Writing
from pinecall_runtime.wire.base import BatchedEntry, Entry
from pinecall_runtime.wire.events import Custom


async def test_a_line_written_after_the_writer_closed_is_refused_and_named(caplog: pytest.LogCaptureFixture) -> None:
    async def append_many(entries: list[BatchedEntry], *, after: int) -> list[Entry]:
        raise AssertionError("nothing is sent after the writer closed")

    writing = Writing(append_many, "call_x")
    writing.open()
    await writing.close(1.0)

    with caplog.at_level(logging.WARNING):
        written = writing.write("custom", Custom(name="too-late", data={}))

    with pytest.raises(ServiceUnavailable):
        await written
    assert "call call_x: the log refused a batch of 1 (custom 'too-late')" in caplog.text
    assert writing.refused == ["custom 'too-late'"]
