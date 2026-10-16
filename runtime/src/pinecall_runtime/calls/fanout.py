"""The live readers of one log or feed: each a queue in seq order, dropped when it falls behind."""

import asyncio
from collections.abc import Callable
from dataclasses import dataclass
from typing import Self

from pinecall_runtime.wire.base import Entry
from pinecall_runtime.wire.events import TERMINAL_EVENT

# How far a reader may fall behind before it is dropped: about a minute of a busy call, and the
# most a dead socket can pin.
QUEUE_DEPTH = 256

# A reader that filtered these out could wait forever on a log that already ended.
ALWAYS_PASS = frozenset({"log.gap", "log.caught_up", "call.ended", TERMINAL_EVENT})


@dataclass(frozen=True, slots=True)
class Filter:
    """One reader's filter: the types it wants (None for every one), whether only durable, and whether strictly so."""

    types: frozenset[str] | None = None
    durable: bool = False
    # A call's reader is told the call ended whatever it asked for; the org's feed never ends, and a
    # reader of one type there has no shape for another call's ending.
    strict: bool = False

    def passes(self, entry: Entry) -> bool:
        """Whether the entry reaches this reader."""
        if not self.strict and entry.type in ALWAYS_PASS:
            return True
        if self.durable and entry.ephemeral:
            return False
        return self.types is None or entry.type in self.types


EVERYTHING = Filter()


class Subscription:
    """One live reader's queue; iteration ends when the log closes or the reader fell behind."""

    def __init__(
        self, only: Filter, leave: Callable[["Subscription"], None], after: Callable[[], None] | None = None
    ) -> None:
        """Keep the filter, the way out of the fanout, and what to do once out (unfollow)."""
        self.only = only
        self.dropped = False
        self._leave = leave
        self._after = after
        self._ended = False
        self._left = False
        # One slot past the depth for the end marker, so closing a full queue never blocks.
        self._queue: asyncio.Queue[Entry | None] = asyncio.Queue(maxsize=QUEUE_DEPTH + 1)

    def offer(self, entry: Entry) -> bool:
        """Queue the entry if the filter passes it; False once this reader is gone."""
        if self._ended:
            return False
        if not self.only.passes(entry):
            return True
        if self._queue.qsize() >= QUEUE_DEPTH:
            self.dropped = True
            self._end()
            return False
        self._queue.put_nowait(entry)
        return True

    def close(self) -> None:
        """End the iteration after what is queued, and leave the fanout."""
        self._end()
        self._leave(self)
        if not self._left:
            self._left = True
            if self._after is not None:
                self._after()

    def _end(self) -> None:
        if not self._ended:
            self._ended = True
            self._queue.put_nowait(None)

    def __aiter__(self) -> Self:
        return self

    async def __anext__(self) -> Entry:
        """The next entry in log order; the end marker ends the iteration."""
        entry = await self._queue.get()
        if entry is None:
            raise StopAsyncIteration
        return entry


class Fanout:
    """The live readers of one log or feed; publishing never waits for any of them."""

    def __init__(self) -> None:
        """Start with no reader."""
        self._readers: set[Subscription] = set()
        self._closed = False

    @property
    def readers(self) -> int:
        """How many readers are subscribed."""
        return len(self._readers)

    def subscribe(self, only: Filter = EVERYTHING, after: Callable[[], None] | None = None) -> Subscription:
        """A reader of what is published from now on; on a closed fanout, an ended one."""
        subscription = Subscription(only, self._readers.discard, after)
        if self._closed:
            subscription.close()
        else:
            self._readers.add(subscription)
        return subscription

    def publish(self, entry: Entry) -> None:
        """Offer the entry to every reader, dropping the ones that fell behind."""
        for reader in tuple(self._readers):
            if not reader.offer(entry):
                reader.close()

    def close(self) -> None:
        """End every reader after what it was given; a later subscriber gets nothing."""
        self._closed = True
        for reader in tuple(self._readers):
            reader.close()
        self._readers.clear()

    def drop(self) -> None:
        """End every reader as one that fell behind: each resumes from the store."""
        for reader in tuple(self._readers):
            reader.dropped = True
            reader.close()
        self._readers.clear()
