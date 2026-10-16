"""A call's entries in the order they happened, sent to its log in batches by one task."""

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable

from livekit.agents.utils import aio

from pinecall_runtime.exceptions import ServiceUnavailable
from pinecall_runtime.wire.base import BatchedEntry, Entry, WireModel
from pinecall_runtime.wire.events import EPHEMERAL_EVENTS

logger = logging.getLogger(__name__)

# Called as `append_many(entries, after=...)`, as the call's log is: the entries numbered, in the
# order they were sent.
type AppendMany = Callable[..., Awaitable[list[Entry]]]

# What one request carries: whatever is queued when the last one was answered, up to this.
MOST_A_BATCH = 64
# Past this many waiting, an ephemeral entry is shed: no store keeps it. A durable one is always
# queued, so a gateway that was away never leaves a hole in the log.
MOST_QUEUED = 4096
SHED = "call {call}: {queued} entries wait for the log, so {kind} was shed"
# What a call waits for its log to take what it wrote; past it, at the end, the gateway's reaper
# seals what the call could not.
WRITTEN_WITHIN_S = 20.0


class Writing:
    """The call's entries in the order they happened, sent to the log in batches."""

    # livekit calls most listeners synchronously; one queue drained by one task keeps order. A
    # writer that takes over a call another wrote to follows on from what the log took from it.
    def __init__(self, append_many: AppendMany, call: str, *, after: int = 0) -> None:
        """An empty queue for the call, drained once `open` starts it."""
        self.append_many = append_many
        self.call = call
        self.queued: asyncio.Queue[tuple[BatchedEntry, asyncio.Future[Entry]]] = asyncio.Queue()
        self.draining: asyncio.Task[None] | None = None
        # How many entries the log took from this call's writer: what the next batch follows.
        self.after = after
        self.refused: list[str] = []
        self.shed: list[str] = []

    def open(self) -> None:
        """Start sending."""
        if self.draining is None:
            self.draining = asyncio.create_task(self._drain())

    # livekit calls most listeners synchronously: they queue and move on; a caller that needs
    # the entry (its seq) awaits the future. The stamp is when it happened, not when it was sent.
    def write(self, kind: str, event: WireModel, *, ephemeral: bool | None = None) -> asyncio.Future[Entry]:
        """Queue an entry; the future is the entry once the log holds it."""
        written: asyncio.Future[Entry] = asyncio.get_running_loop().create_future()
        forgettable = kind in EPHEMERAL_EVENTS if ephemeral is None else ephemeral
        waiting = self.queued.qsize()
        if forgettable and waiting >= MOST_QUEUED:
            self.shed.append(kind)
            _refuse(written, ServiceUnavailable(SHED.format(call=self.call, queued=waiting, kind=kind)))
            return written
        entry = BatchedEntry(type=kind, data=event.dump(), ephemeral=ephemeral, ts=time.time())
        self.queued.put_nowait((entry, written))
        return written

    async def flush(self, within_s: float) -> None:
        """Wait until every queued entry was sent; TimeoutError past `within_s`."""
        await asyncio.wait_for(self.queued.join(), within_s)

    async def close(self, within_s: float) -> None:
        """Send what is queued for up to `within_s`, then stop and say what never went."""
        try:
            await self.flush(within_s)
        except TimeoutError:
            logger.warning(
                "call %s: %d entries never reached the log within %gs", self.call, self.queued.qsize(), within_s
            )
        if self.draining is not None:
            await aio.cancel_and_wait(self.draining)
            self.draining = None
        if self.refused:
            refused = ", ".join(sorted(set(self.refused)))
            logger.warning("call %s: the log refused %d entries (%s)", self.call, len(self.refused), refused)
        if self.shed:
            shed = ", ".join(sorted(set(self.shed)))
            logger.warning(
                "call %s: %d ephemeral entries were shed at the queue's ceiling (%s)", self.call, len(self.shed), shed
            )

    # No timer: while one batch is out the next one fills, so an idle call sends each entry
    # alone and a busy one batches itself.
    async def _drain(self) -> None:
        while True:
            batch = [await self.queued.get()]
            while len(batch) < MOST_A_BATCH and not self.queued.empty():
                batch.append(self.queued.get_nowait())
            try:
                await self._send(batch)
            finally:
                for _ in batch:
                    self.queued.task_done()

    # A refused batch never ends the call: the client retries what is transient with the same
    # `after`, so what fails here is a refusal of the whole batch, counted and named at close.
    async def _send(self, batch: list[tuple[BatchedEntry, asyncio.Future[Entry]]]) -> None:
        kinds = [entry.type for entry, _ in batch]
        try:
            numbered = await self.append_many([entry for entry, _ in batch], after=self.after)
        except asyncio.CancelledError:
            self.refused += kinds
            raise
        except Exception as refused:
            logger.warning("call %s: the log refused a batch of %d", self.call, len(batch), exc_info=True)
            self.refused += kinds
            for _, written in batch:
                if not written.done():
                    _refuse(written, refused)
            return
        self.after += len(batch)
        for (_, written), entry in zip(batch, numbered, strict=True):
            if not written.done():
                written.set_result(entry)


# Most entries are queued and never awaited: read here, the refusal is not logged a second time
# by asyncio as an exception nobody retrieved. `close` names what was refused and what was shed.
def _refuse(written: asyncio.Future[Entry], why: Exception) -> None:
    written.set_exception(why)
    written.exception()
