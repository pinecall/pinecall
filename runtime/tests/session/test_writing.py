"""A call's writer: entries in the order they happened, batched, shed at its ceiling, and refused by name."""

import asyncio
import gc
import logging
from dataclasses import dataclass, field

import pytest

from runtime.calls.log.log import Log
from runtime.calls.log.store import Store
from runtime.exceptions import Conflict, ServiceUnavailable
from runtime.session.writing import MOST_A_BATCH, MOST_QUEUED, Writing
from runtime.wire.base import BatchedEntry, Entry
from runtime.wire.events import Custom, UserTranscript
from tests.conftest import needs_the_database
from tests.session.conftest import Box


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


def _custom(name: str) -> Custom:
    return Custom(name=name, data={})


@needs_the_database
async def test_entries_queued_from_sync_callbacks_reach_the_log_in_that_order(
    box: Box, store: Store, call: str
) -> None:
    writing = Writing(box.log.append_many, call)
    writing.open()
    for name in ("uno", "dos", "tres"):
        writing.write("custom", _custom(name))
    await writing.close(5)
    assert [entry.data["name"] for entry in await store.whole_of(call)] == ["uno", "dos", "tres"]


@needs_the_database
async def test_an_entry_waited_for_comes_back_with_the_seq_the_log_gave_it(box: Box, call: str) -> None:
    writing = Writing(box.log.append_many, call)
    writing.open()
    entry = await writing.write("custom", _custom("uno"))
    await writing.close(5)
    assert entry.seq > 0


@dataclass
class Batches:
    """The call's real log, the size of each batch it was sent, and a gate on the first."""

    log: Log
    sizes: list[int] = field(default_factory=list[int])
    first_out: asyncio.Event = field(default_factory=asyncio.Event)
    let_go: asyncio.Event = field(default_factory=asyncio.Event)

    async def append_many(self, entries: list[BatchedEntry], *, after: int) -> list[Entry]:
        """Count the batch, hold the first until let go, then write it on the log."""
        self.sizes.append(len(entries))
        if len(self.sizes) == 1:
            self.first_out.set()
            await self.let_go.wait()
        return await self.log.append_many(entries, after=after)


@needs_the_database
async def test_what_is_queued_while_a_batch_is_out_goes_in_the_next_one_in_order(
    box: Box, store: Store, call: str
) -> None:
    batches = Batches(box.log)
    writing = Writing(batches.append_many, call)
    writing.open()
    written = [writing.write("custom", _custom("uno"))]
    await batches.first_out.wait()
    written += [writing.write("custom", _custom(name)) for name in ("dos", "tres", "cuatro")]
    batches.let_go.set()
    await writing.close(5)
    assert batches.sizes == [1, 3]
    assert [entry.data["name"] for entry in await store.whole_of(call)] == [
        "uno",
        "dos",
        "tres",
        "cuatro",
    ]
    assert [future.result().seq for future in written] == [1, 2, 3, 4]
    assert writing.after == 4


@needs_the_database
async def test_a_batch_carries_at_most_its_ceiling_and_the_rest_follow(box: Box, store: Store, call: str) -> None:
    batches = Batches(box.log)
    batches.let_go.set()
    writing = Writing(batches.append_many, call)
    for n in range(MOST_A_BATCH * 2 + 3):
        writing.write("custom", _custom(str(n)))
    writing.open()
    await writing.close(5)
    assert batches.sizes == [MOST_A_BATCH, MOST_A_BATCH, 3]
    names = [entry.data["name"] for entry in await store.whole_of(call)]
    assert names == [str(n) for n in range(MOST_A_BATCH * 2 + 3)]


@needs_the_database
async def test_an_entry_of_an_idle_call_goes_alone(box: Box, call: str) -> None:
    batches = Batches(box.log)
    batches.let_go.set()
    writing = Writing(batches.append_many, call)
    writing.open()
    await writing.write("custom", _custom("uno"))
    await writing.write("custom", _custom("dos"))
    await writing.close(5)
    assert batches.sizes == [1, 1]


async def test_a_refused_batch_refuses_each_of_its_entries_and_the_next_still_goes() -> None:
    kept: list[str] = []

    async def picky(entries: list[BatchedEntry], *, after: int) -> list[Entry]:
        if any(entry.data.get("name") == "no" for entry in entries):
            raise Conflict("refused")
        kept.extend(str(entry.data["name"]) for entry in entries)
        return [
            Entry(
                seq=after + place,
                ts=entry.ts,
                call="c",
                agent="a",
                type=entry.type,
                ephemeral=bool(entry.ephemeral),
                data=entry.data,
            )
            for place, entry in enumerate(entries, 1)
        ]

    writing = Writing(picky, "c")
    refused = [writing.write("custom", _custom("no")), writing.write("custom", _custom("tampoco"))]
    writing.open()
    await asyncio.gather(*refused, return_exceptions=True)
    taken = await writing.write("custom", _custom("también"))
    await writing.close(5)
    assert kept == ["también"]
    assert writing.refused == ["custom 'no'", "custom 'tampoco'"]
    assert all(isinstance(future.exception(), Conflict) for future in refused)
    assert (taken.seq, writing.after) == (1, 1)


async def test_at_the_ceiling_an_ephemeral_entry_is_shed_and_a_durable_one_is_queued() -> None:
    async def stuck(entries: list[BatchedEntry], *, after: int) -> list[Entry]:
        del entries, after
        await asyncio.sleep(60)
        raise AssertionError

    writing = Writing(stuck, "c")
    for n in range(MOST_QUEUED):
        writing.write("custom", _custom(str(n)))
    heard = writing.write("user.transcript", UserTranscript(text="ho", final=False))
    kept = writing.write("custom", _custom("durable"))
    assert isinstance(heard.exception(), ServiceUnavailable)
    assert writing.shed == ["user.transcript"]
    assert not kept.done()
    assert writing.queued.qsize() == MOST_QUEUED + 1
    await writing.close(0.01)


# asyncio logs an exception nobody retrieved when its future is collected: once per shed entry.
async def test_a_shed_entry_nobody_waits_for_is_not_logged_as_an_exception_never_retrieved(
    caplog: pytest.LogCaptureFixture,
) -> None:
    async def stuck(entries: list[BatchedEntry], *, after: int) -> list[Entry]:
        del entries, after
        await asyncio.sleep(60)
        raise AssertionError

    writing = Writing(stuck, "c")
    for n in range(MOST_QUEUED):
        writing.write("custom", _custom(str(n)))
    writing.write("user.transcript", UserTranscript(text="ho", final=False))
    gc.collect()
    await asyncio.sleep(0)
    assert [record.getMessage() for record in caplog.records if record.name == "asyncio"] == []
    assert writing.shed == ["user.transcript"]
    await writing.close(0.01)


async def test_a_close_past_its_budget_lets_the_queue_go_rather_than_wait_for_ever() -> None:
    async def stuck(entries: list[BatchedEntry], *, after: int) -> list[Entry]:
        del entries, after
        await asyncio.sleep(60)
        raise AssertionError

    writing = Writing(stuck, "c")
    writing.open()
    writing.write("custom", _custom("uno"))
    writing.write("custom", _custom("dos"))
    await asyncio.wait_for(writing.close(0.05), 1)
    assert writing.draining is None
    assert writing.refused == ["custom 'uno'", "custom 'dos'"]


# An app's line logged after the log was sealed is lost; its name is what the warning keeps of it.
async def test_a_line_the_sealed_log_refused_is_named_in_what_is_logged(caplog: pytest.LogCaptureFixture) -> None:
    async def sealed(entries: list[BatchedEntry], *, after: int) -> list[Entry]:
        del entries
        raise Conflict(f"call call_1 has ended: its batch cannot be appended after {after}")

    writing = Writing(sealed, "call_1")
    writing.open()
    lost = writing.write("custom", _custom("closed"))
    with pytest.raises(Conflict):
        await lost
    await writing.close(5)
    assert "the log refused a batch of 1 (custom 'closed')" in caplog.text
    assert "the log refused 1 entries (custom 'closed')" in caplog.text
