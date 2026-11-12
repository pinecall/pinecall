"""The logs open in this process, by name: one for a call's writer and its readers, pruned when nobody holds them."""

import contextlib
from collections.abc import AsyncGenerator

from runtime.calls.context import log_name
from runtime.calls.log.fanout import EVERYTHING, Filter
from runtime.calls.log.feeds import Feeds
from runtime.calls.log.log import Log
from runtime.calls.log.relay import Relay
from runtime.calls.log.store import Store
from runtime.wire.base import Entry


class Logs:
    """The logs of this process by name: a call's for its writer, anybody's for a reader, an agent's own."""

    def __init__(self, store: Store, relay: Relay, feeds: Feeds) -> None:
        """Start with no log open; what a held log writes is carried on the feeds."""
        self._store = store
        self._relay = relay
        self._feeds = feeds
        self._logs: dict[str, Log] = {}

    @property
    def readers(self) -> int:
        """How many live readers the logs of this process hold."""
        return sum(log.fanout.readers for log in self._logs.values())

    def writing(self, call: str, agent: str) -> Log:
        """The call's log for its writer, held until the process forgets the call."""
        log = self._log(call, agent)
        log.agent = agent
        return self._hold(log)

    def reading(self, call: str) -> Log:
        """The call's log for a reader, whoever writes it."""
        self._prune(but=call)
        return self._log(call, "")

    # The log is looked up when the reader starts, never when its request came in: a log handed
    # out and not yet subscribed has no reader, so another request's prune drops it, and a reader
    # that subscribes to the dropped copy hears nothing live, its call's end included. Nothing
    # awaits between the lookup and the subscription, so no prune runs in between.
    async def stream(self, call: str, *, after: int = 0, only: Filter = EVERYTHING) -> AsyncGenerator[Entry]:
        """A reader of the call's log: the backlog above the cursor, log.caught_up, then what is written."""
        async with contextlib.aclosing(self.reading(call).stream(after=after, only=only)) as entries:
            async for entry in entries:
                yield entry

    def agent(self, slug: str) -> Log:
        """The agent's own log, for writing or reading."""
        self._prune(but=log_name(None, slug))
        return self._hold(self._log(None, slug))

    def forget(self, call: str) -> None:
        """Drop the call's log, its readers and its cached owner."""
        self._logs.pop(call, None)
        self._feeds.forget(call)

    def _log(self, call: str | None, agent: str) -> Log:
        name = log_name(call, agent)
        log = self._logs.get(name)
        if log is None:
            log = self._logs[name] = Log(self._store, call, agent, self._relay)
        return log

    # A held log is one this process writes: every entry it takes is carried on the feeds.
    def _hold(self, log: Log) -> Log:
        if not log.kept_open:
            log.kept_open = True
            log.tap(self._feeds.carry)
        return log

    # On every read, so readers asking for arbitrary names cannot grow the table without bound.
    def _prune(self, *, but: str = "") -> None:
        idle = [
            name
            for name, log in self._logs.items()
            if name != but and not log.kept_open and not log.fanout.readers and not log.streams
        ]
        for name in idle:
            del self._logs[name]
