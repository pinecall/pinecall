"""One log open in this process: a call's, or an agent's own; written here, read live here, replayed from the store."""

from collections.abc import AsyncGenerator, Awaitable, Callable, Sequence
from typing import overload

from runtime.agents.declaration import Declaration
from runtime.calls.context import log_name
from runtime.calls.folds.state import apply, initial_state
from runtime.calls.log.fanout import EVERYTHING, Fanout, Filter, Subscription
from runtime.calls.log.private import NoPrivacy, Privacy
from runtime.calls.log.relay import Relay, log_channel
from runtime.calls.log.store import Store
from runtime.calls.log.writer import Guarded, Sure, Unnumbered
from runtime.exceptions import ValidationError
from runtime.kit.crypto import Vault
from runtime.kit.text import JsonObject
from runtime.signal import LocalSignal
from runtime.wire.base import BatchedEntry, Entry
from runtime.wire.events import EPHEMERAL_EVENTS, TERMINAL_EVENT
from runtime.wire.state import State

# Runs inline on every append, before append returns: for work that is part of the write.
type Tap = Callable[[Entry], Awaitable[None]]


# Readers and the writer share the one Log of a name: a reader often arrives before the writer.
class Log:
    """One call's log, or one agent's: written here, read live here, replayed from the store."""

    def __init__(self, store: Store, call: str | None, agent: str, relay: Relay | None = None) -> None:
        """Name the log: a call's, or an agent's own when call is None; with no relay, one of this process alone."""
        self.call = call
        self.agent = agent
        self.name = log_name(call, agent)
        self.fanout = Fanout()
        self.sealed = False
        # Set by whoever holds the log for its writer: a held log outlives its readers until the
        # process forgets it.
        self.kept_open = False
        # The streams reading it now. A stream's reader leaves the fanout for a moment when it falls
        # behind and follows again; the log is not pruned in between.
        self.streams = 0
        # What it masks by, once the call's writer says what the agent declared (`mask_by`).
        self.privacy: Privacy | NoPrivacy = NoPrivacy(store, self.name)
        self._store = store
        # The same clock for an entry, a marker and a piece of news: a test's clock moves them all.
        self.clock = store.clock
        # A log made alone hears its own appends only: a relay of its own, on a signal nobody else is on.
        self._relay = relay or Relay(LocalSignal(), store)
        self._channel = log_channel(self.name)
        self._taps: list[Tap] = []
        # The state as last folded, under the head's seq it was folded at.
        self._snapshot: tuple[int, State] | None = None

    def tap(self, tap: Tap) -> None:
        """Run the tap on every append from now on, before append returns."""
        self._taps.append(tap)

    # Said by the call's writer when it serves the call; a log nobody said it for masks nothing.
    def mask_by(self, vault: Vault, declaration: Declaration) -> None:
        """Mask what the declaration names private from now on, and seal it aside under the vault."""
        self.privacy = Privacy(self._store, self.name, vault, declaration)

    # ── written here ──

    async def append(self, kind: str, data: JsonObject | None = None, *, ephemeral: bool | None = None) -> Entry:
        """Write the entry, its private values masked, publish it, run the taps, seal at the end."""
        forgettable = kind in EPHEMERAL_EVENTS if ephemeral is None else ephemeral
        return await self._write("entry", kind, data or {}, ephemeral=forgettable)

    # Two writers deciding the same end (a webhook delivered twice) write it once.
    async def append_first(self, kind: str, data: JsonObject) -> Entry | None:
        """Write and publish a durable entry unless the log holds one of its type; None then."""
        if self.call is None:
            raise ValidationError(f"agent {self.agent}: only a call's log is looked at")
        return await self._write("first", kind, data)

    # Once per call id, whichever gateway writes it: the app's answer where its socket is, or the
    # timeout where the worker asked.
    async def answer(self, data: JsonObject) -> Entry | None:
        """Write and publish a tool.result unless the log holds its answer already; None then."""
        if self.call is None:
            raise ValidationError(f"agent {self.agent}: only a call's log asks tools")
        return await self._write("answer", "tool.result", data)

    # Until 2026-11 a verdict given again was written past the log, by the store alone: no reader of
    # the call heard it, the org's feed did not redraw its row, and the usage's reader slept on it.
    async def rescore(self, data: JsonObject) -> Entry:
        """Write and publish a call.score on a log already judged: the one entry a sealed log still takes."""
        if self.call is None:
            raise ValidationError(f"agent {self.agent}: only a call's log is judged")
        return await self._write("score", TERMINAL_EVENT, data)

    # A replayed batch was published when it was first taken: publishing it again would repeat
    # it. Its private values are sealed aside after it is published and again on a replay, which
    # keeps the ones kept already: a batch whose seal broke is kept whole by the worker's retry.
    async def append_many(self, entries: Sequence[BatchedEntry], *, after: int) -> list[Entry]:
        """Write a worker's batch once, then publish and tap each entry in order as append does."""
        masked = await self.privacy.mask_all([(item.type, item.data) for item in entries])
        unnumbered = [
            Unnumbered(
                type=item.type,
                data=kept.kept,
                ephemeral=item.type in EPHEMERAL_EVENTS if item.ephemeral is None else item.ephemeral,
                ts=item.ts,
            )
            for item, kept in zip(entries, masked, strict=True)
        ]
        batch = await self._store.write_many(self.call, self.agent, unnumbered, after=after)
        aside = self.privacy.remember(zip(batch.entries, masked, strict=True))
        if not batch.replayed:
            for entry in batch.entries:
                await self._tell(entry, ends=True)
        await self.privacy.seal_aside(aside)
        return batch.entries

    # An entry stored by a gateway that may have died before telling the others: told again. A
    # reader that heard it already skips it by its seq.
    def republish(self, entry: Entry) -> None:
        """Publish a stored entry once more to every gateway's readers."""
        self._relay.tell(self._channel, entry)

    async def seal(self) -> None:
        """Seal the call's log in the store and end every live reader."""
        if self.call is None:
            raise ValidationError(f"agent {self.agent}: an agent's log has no end")
        self.sealed = True
        await self._store.seal(self.call)
        self.fanout.close()

    @overload
    async def _write(self, how: Sure, kind: str, data: JsonObject, *, ephemeral: bool = False) -> Entry: ...

    @overload
    async def _write(self, how: Guarded, kind: str, data: JsonObject, *, ephemeral: bool = False) -> Entry | None: ...

    # The one way an entry is written here, whichever of the writer's ways it is. Stored before
    # published, so no reader sees an entry the store lacks and every cursor resumes. A private value
    # is sealed aside before the entry is published: a tool call whose seal broke never reached the
    # app, so the worker's retry runs the tool once.
    async def _write(
        self, how: Sure | Guarded, kind: str, data: JsonObject, *, ephemeral: bool = False
    ) -> Entry | None:
        masked = await self.privacy.mask(kind, data)
        entry = await self._store.write(how, self.call, self.agent, kind, masked.kept, ephemeral=ephemeral)
        if entry is not None:
            await self.privacy.keep([(entry, masked)])
            await self._tell(entry, ends=how != "score")
        return entry

    # A verdict given again lands on a log sealed already: it is told and tapped, and seals nothing.
    async def _tell(self, entry: Entry, *, ends: bool) -> None:
        self._relay.tell(self._channel, entry)
        for tap in list(self._taps):
            await tap(entry)
        if ends and entry.type == TERMINAL_EVENT and self.call is not None:
            await self.seal()

    # ── heard here ──

    # What the relay hands on, this process's own appends included: the log's readers hear it, and
    # the entry that ends the call ends them, sealed here or on another gateway.
    def publish(self, entry: Entry) -> None:
        """Hand one entry of the log to its live readers; the terminal one ends them."""
        self.fanout.publish(entry)
        if entry.type == TERMINAL_EVENT and self.call is not None:
            self.sealed = True
            self.fanout.close()

    def drop(self) -> None:
        """The log's channel was lost: every reader resumes from the store."""
        self.fanout.drop()

    # ── read here ──

    # Subscribed first, so no prune drops a log whose reader waits on the signal (it would hear nothing,
    # its call's end included); confirmed before the backlog is read, so another gateway's commits are heard.
    async def follow(self, only: Filter = EVERYTHING) -> Subscription:
        """A live reader that hears what any gateway writes to this log, from now on."""
        reader = self.fanout.subscribe(only, after=lambda: self._relay.unfollow(self._channel, self))
        return await self._relay.follow_log(self.name, self, reader)

    # Each pass: follow, the backlog, what is written live; a reader that fell behind is told the
    # gap and follows again.
    async def stream(self, *, after: int = 0, only: Filter = EVERYTHING) -> AsyncGenerator[Entry]:
        """The backlog above the cursor, log.caught_up, then what is written from then on."""
        cursor = after
        self.streams += 1
        try:
            while True:
                # Subscribed before the backlog is read, so nothing written between the two is lost.
                subscription = await self.follow(only)
                try:
                    # Asked before the backlog: a log sealed by then is whole in it, and one sealed
                    # after ends its readers here, once they drained what they were given.
                    over = self.sealed or await self._store.is_sealed(self.name)
                    for entry in await self._store.whole_of(self.name, after=cursor):
                        cursor = entry.seq
                        self.agent = self.agent or entry.agent
                        if only.passes(entry):
                            yield entry
                    if not self.agent and cursor:
                        self.agent = await self._agent_of(cursor)
                    yield self._mark(cursor, "log.caught_up", {"seq": cursor})
                    if over:
                        return
                    async for entry in subscription:
                        if entry.seq > cursor:
                            cursor = entry.seq
                            yield entry
                    if not subscription.dropped:
                        return
                finally:
                    subscription.close()
                gap = await self._gap_from(cursor)
                yield gap
                cursor = gap.seq
        finally:
            self.streams -= 1

    # Compared against the store's seq, ephemerals counted, or a live call never hits the memo. A
    # log that moved is folded on from where the memo stands, on a copy: whoever holds the state
    # handed out before keeps it as it was. Until 2026-11 it was folded again from its first entry.
    async def snapshot(self) -> State:
        """The state the log reduces to, folded on only when the log moved."""
        latest = await self._store.seq_of(self.name)
        if self._snapshot is None or self._snapshot[0] != latest:
            state = initial_state() if self._snapshot is None else self._snapshot[1].model_copy(deep=True)
            for entry in await self._store.whole_of(self.name, after=state.seq):
                state = apply(state, entry)
            self._snapshot = latest, state
        return self._snapshot[1]

    # Fell behind: a gap says what was missed and, for a call, carries the state instead of the
    # entries. An agent's log reduces to no state, so its gap re-reads the store.
    async def _gap_from(self, cursor: int) -> Entry:
        if self.call is None:
            return self._mark(cursor, "log.gap", {"from_seq": cursor + 1, "to_seq": cursor, "snapshot": None})
        to_seq = max(await self._store.seq_of(self.name), cursor)
        snapshot = (await self.snapshot()).dump()
        return self._mark(to_seq, "log.gap", {"from_seq": cursor + 1, "to_seq": to_seq, "snapshot": snapshot})

    # A reader's log is made before anybody says whose it is: a marker names the agent its entries do.
    async def _agent_of(self, seq: int) -> str:
        said = await self._store.page_of(self.name, after=seq - 1, limit=1)
        return said[0].agent if said else ""

    def _mark(self, seq: int, kind: str, data: JsonObject) -> Entry:
        return Entry(seq=seq, ts=self.clock(), call=self.call, agent=self.agent, type=kind, ephemeral=True, data=data)
