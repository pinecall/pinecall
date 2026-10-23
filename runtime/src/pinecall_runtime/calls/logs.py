"""The logs open in this process: append, the live readers, replay, the feeds."""

import time
from collections.abc import AsyncIterator, Awaitable, Callable, Iterable, Sequence

from pinecall_runtime.calls import private
from pinecall_runtime.calls.fanout import EVERYTHING, Fanout, Filter, Subscription
from pinecall_runtime.calls.models import log_name
from pinecall_runtime.calls.reducer import reduce
from pinecall_runtime.calls.relay import (
    BOX_CHANNEL,
    CHANNEL,
    FEED_CHANNEL,
    FEED_PREFIX,
    LOG_PREFIX,
    USAGE_CHANNEL,
    Relay,
)
from pinecall_runtime.calls.repository.heads import Claimant
from pinecall_runtime.calls.store import Store
from pinecall_runtime.calls.writer import METERED_TYPES, Unnumbered
from pinecall_runtime.enums import Env
from pinecall_runtime.exceptions import ValidationError
from pinecall_runtime.kit.auth import Scope
from pinecall_runtime.kit.text import JsonObject
from pinecall_runtime.redis import LocalSignal, Signal
from pinecall_runtime.wire.base import BatchedEntry, Entry, WireModel
from pinecall_runtime.wire.events import EPHEMERAL_EVENTS, TERMINAL_EVENT
from pinecall_runtime.wire.feed import ToolFailed, ToolRan
from pinecall_runtime.wire.parts import ToolResult
from pinecall_runtime.wire.state import State

# Runs inline on every append, before append returns: for work that is part of the write.
type Tap = Callable[[Entry], Awaitable[None]]

# A call sealed and a call judged: a list redraws its row then, so they are on the feed, with no
# data, since the outcome and the verdicts are the call's content; a reader reads them off the call.
ONLY_THAT_IT_HAPPENED = frozenset({"call.summary", "call.score"})

# What an org's feed and the box's carry: the lifecycle, never the content of a call.
ORG_EVENTS = frozenset(
    {
        "agent.registered",
        "agent.detached",
        "call.ringing",
        "call.dialing",
        "call.started",
        "call.ended",
        "attention.requested",
        "attention.answered",
        "supervisor.took_over",
        "supervisor.released",
        "call.summary",
        "call.score",
    }
)


# Readers and the writer share the one Log of a name: a reader often arrives before the writer.
class Log:
    """One call's log, or one agent's: written here, read live here, replayed from the store."""

    def __init__(self, store: Store, call: str | None, agent: str, relay: Relay | None = None) -> None:
        """Name the log: a call's, or an agent's own when call is None; alone with no relay."""
        self.call = call
        self.agent = agent
        self.name = log_name(call, agent)
        self.fanout = Fanout()
        self.sealed = False
        # Set by Logs.writing: a held log outlives its readers until the process forgets it.
        self.kept_open = False
        # Set by the call's writer: what it masks by. None on a log nobody declared anything for.
        self.privacy: private.Privacy | None = None
        # The private values of the entries appended or opened here, by seq, for the app's socket.
        self.private_values: dict[int, JsonObject] = {}
        self._store = store
        self.clock = store.clock
        # None: a log of this process alone, its readers hearing its own appends only.
        self._relay = relay
        self._taps: list[Tap] = []
        self._snapshot: tuple[int, State] | None = None

    def tap(self, tap: Tap) -> None:
        """Run the tap on every append from now on, before append returns."""
        self._taps.append(tap)

    # Stored before published, so no reader sees an entry the store lacks and every cursor
    # resumes. A private value is sealed aside before the entry is published: a tool call whose
    # seal broke never reached the app, so the worker's retry runs the tool once.
    async def append(self, kind: str, data: JsonObject | None = None, *, ephemeral: bool | None = None) -> Entry:
        """Write the entry, its private values masked, publish it, run the taps, seal at the end."""
        forgettable = kind in EPHEMERAL_EVENTS if ephemeral is None else ephemeral
        await self._knowing([kind])
        written = self._split(kind, data or {})
        entry = await self._store.append(self.call, self.agent, kind, written.kept, ephemeral=forgettable)
        await self._seal_aside(self._keep_open([(entry, written)]))
        await self._publish(entry)
        return entry

    # Two writers deciding the same end (a webhook delivered twice) write it once.
    async def append_first(self, kind: str, data: JsonObject) -> Entry | None:
        """Write and publish a durable entry unless the log holds one of its type; None then."""
        if self.call is None:
            raise ValidationError(f"agent {self.agent}: only a call's log is looked at")
        await self._knowing([kind])
        written = self._split(kind, data)
        entry = await self._store.append_first(self.call, self.agent, kind, written.kept)
        if entry is not None:
            await self._seal_aside(self._keep_open([(entry, written)]))
            await self._publish(entry)
        return entry

    # Once per call id, whichever gateway writes it: the app's answer where its socket is, or the
    # timeout where the worker asked.
    async def answer(self, data: JsonObject) -> Entry | None:
        """Write and publish a tool.result unless the log holds its answer already; None then."""
        if self.call is None:
            raise ValidationError(f"agent {self.agent}: only a call's log asks tools")
        await self._knowing(["tool.result"])
        written = self._split("tool.result", data)
        entry = await self._store.append_answer(self.call, self.agent, written.kept)
        if entry is not None:
            await self._seal_aside(self._keep_open([(entry, written)]))
            await self._publish(entry)
        return entry

    # An entry stored by a gateway that may have died before telling the others: told again. A
    # reader that heard it already skips it by its seq.
    def republish(self, entry: Entry) -> None:
        """Publish a stored entry once more to every gateway's readers."""
        if self._relay is None:
            self.fanout.publish(entry)
        else:
            self._relay.local(CHANNEL.format(name=self.name), entry)

    # A replayed batch was published when it was first taken: publishing it again would repeat
    # it. Its private values are sealed aside after it is published and again on a replay, which
    # keeps the ones kept already: a batch whose seal broke is kept whole by the worker's retry.
    async def append_many(self, entries: Sequence[BatchedEntry], *, after: int) -> list[Entry]:
        """Write a worker's batch once, then publish and tap each entry in order as append does."""
        await self._knowing([item.type for item in entries])
        written = [self._split(item.type, item.data) for item in entries]
        unnumbered = [
            Unnumbered(
                type=item.type,
                data=kept.kept,
                ephemeral=item.type in EPHEMERAL_EVENTS if item.ephemeral is None else item.ephemeral,
                ts=item.ts,
            )
            for item, kept in zip(entries, written, strict=True)
        ]
        batch = await self._store.append_many(self.call, self.agent, unnumbered, after=after)
        aside = self._keep_open(zip(batch.entries, written, strict=True))
        if not batch.replayed:
            for entry in batch.entries:
                await self._publish(entry)
        await self._seal_aside(aside)
        return batch.entries

    # An entry another gateway wrote has its values in that gateway's memory and in the store.
    async def opened(self, entry: Entry) -> Entry:
        """The entry as its writer wrote it, for the app's socket: the private values back in."""
        values = self.private_values.get(entry.seq)
        privacy = self.privacy
        if values is None and privacy is not None and privacy.active and private.may_be_private(entry.type):
            values = private.opened_values(privacy.vault, await self._store.private_of_entry(self.name, entry.seq))
            if values:
                self.private_values[entry.seq] = values
        opened = private.restored(entry, values)
        if privacy is not None:
            privacy.learn(opened.type, opened.data)
        return opened

    async def whole(self) -> list[Entry]:
        """Every entry of the log as its writer wrote it, the private values sealed aside opened."""
        if self.privacy is None:
            return await self._store.whole(self.name)
        entries, sealed = await self._store.whole_with_private(self.name)
        opened = private.opened_all(self.privacy.vault, entries, sealed)
        for entry in opened:
            self.privacy.learn(entry.type, entry.data)
        return opened

    async def seal(self) -> None:
        """Seal the call's log in the store and end every live reader."""
        if self.call is None:
            raise ValidationError(f"agent {self.agent}: an agent's log has no end")
        self.sealed = True
        await self._store.seal(self.call)
        self.fanout.close()

    # Compared against the store's seq, ephemerals counted, or a live call never hits the memo.
    async def snapshot(self) -> State:
        """The state the log reduces to, folded again only when the log moved."""
        latest = await self._store.latest_seq(self.name)
        if self._snapshot is None or self._snapshot[0] != latest:
            self._snapshot = latest, reduce(await self._store.whole(self.name))
        return self._snapshot[1]

    # Followed before the fanout is subscribed, so an entry another gateway commits after the
    # backlog is read was published after the subscription was confirmed, and is heard.
    async def follow(self, only: Filter = EVERYTHING) -> Subscription:
        """A live reader that hears what any gateway writes to this log, from now on."""
        if self._relay is None:
            return self.fanout.subscribe(only)
        await self._relay.follow(CHANNEL.format(name=self.name))
        return self.fanout.subscribe(only, after=self._unfollow)

    async def stream(self, *, after: int = 0, only: Filter = EVERYTHING) -> AsyncIterator[Entry]:
        """The backlog above the cursor, log.caught_up, then what is written from then on."""
        cursor = after
        while True:
            # Subscribed before the backlog is read, so nothing written between the two is lost.
            subscription = await self.follow(only)
            try:
                # Asked before the backlog: a log sealed by then is whole in it, and one sealed
                # after ends its readers here, once they drained what they were given.
                over = self.sealed or await self._store.is_sealed(self.name)
                for entry in await self._store.whole(self.name, after=cursor):
                    cursor = entry.seq
                    self.agent = self.agent or entry.agent
                    if only.passes(entry):
                        yield entry
                if not self.agent and cursor:
                    self.agent = await self._said_by(cursor)
                yield self._marker(cursor, "log.caught_up", {"seq": cursor})
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
            # Fell behind: a gap says what was missed and, for a call, carries the state instead
            # of the entries. An agent's log reduces to no state, so its gap re-reads the store.
            if self.call is None:
                yield self._marker(cursor, "log.gap", {"from_seq": cursor + 1, "to_seq": cursor, "snapshot": None})
                continue
            to_seq = max(await self._store.latest_seq(self.name), cursor)
            snapshot = (await self.snapshot()).dump()
            yield self._marker(to_seq, "log.gap", {"from_seq": cursor + 1, "to_seq": to_seq, "snapshot": snapshot})
            cursor = to_seq

    def _split(self, kind: str, data: JsonObject) -> private.Split:
        privacy = self.privacy
        if privacy is None or not privacy.active:
            return private.Split(data, {})
        privacy.learn(kind, data)
        return private.split(kind, data, privacy.config, privacy.secrets())

    # Another gateway may have asked the app for a tool whose arguments are private: what it sealed
    # is read before an entry that could repeat the values is written, or they would go in the clear.
    async def _knowing(self, kinds: Iterable[str]) -> None:
        privacy = self.privacy
        if privacy is None or not privacy.active or not any(private.may_be_private(kind) for kind in kinds):
            return
        for entry, sealed in await self._store.private_tool_calls(self.name, privacy.through):
            opened = private.restored(entry, private.opened_values(privacy.vault, sealed))
            privacy.learn(opened.type, opened.data)
            privacy.through = max(privacy.through, entry.seq)

    def _keep_open(self, written: Iterable[tuple[Entry, private.Split]]) -> list[tuple[int, JsonObject]]:
        aside = [(entry.seq, split.private) for entry, split in written if split.private]
        self.private_values.update(aside)
        return aside

    async def _seal_aside(self, aside: list[tuple[int, JsonObject]]) -> None:
        if self.privacy is not None and aside:
            vault = self.privacy.vault
            await self._store.keep_private(
                self.name, [(seq, private.sealed_values(vault, values)) for seq, values in aside]
            )

    def _unfollow(self) -> None:
        if self._relay is not None:
            self._relay.unfollow(CHANNEL.format(name=self.name))

    async def _publish(self, entry: Entry) -> None:
        if self._relay is None:
            self.fanout.publish(entry)
        else:
            self._relay.local(CHANNEL.format(name=self.name), entry)
        for tap in list(self._taps):
            await tap(entry)
        if entry.type == TERMINAL_EVENT and self.call is not None:
            await self.seal()

    # A reader's log is made before anybody says whose it is: a marker names the agent its entries do.
    async def _said_by(self, seq: int) -> str:
        said = await self._store.since(self.name, after=seq - 1, limit=1)
        return said[0].agent if said else ""

    def _marker(self, seq: int, kind: str, data: JsonObject) -> Entry:
        return Entry(seq=seq, ts=time.time(), call=self.call, agent=self.agent, type=kind, ephemeral=True, data=data)


class Logs:
    """The logs of this process by name, the org feeds and the box's, and who owns what."""

    def __init__(self, store: Store, signal: Signal | None = None) -> None:
        """Start with no log open and no feed listened to; alone with no signal."""
        self.store = store
        self.relay = Relay(
            signal or LocalSignal(),
            lambda log, after, limit: store.since(log, after=after, limit=limit),
            store.latest_seq,
            self._deliver,
            self._drop,
        )
        self.box = Fanout()
        self.metered = Fanout()
        self._logs: dict[str, Log] = {}
        self._feeds: dict[tuple[str, Env], Fanout] = {}
        # A log's owner never changes; caching it keeps a store read off the append path.
        self._owners: dict[str, Claimant] = {}

    @property
    def readers(self) -> int:
        """How many live readers every log and feed of this process holds."""
        fanouts = [self.box, self.metered, *self._feeds.values(), *(log.fanout for log in self._logs.values())]
        return sum(fanout.readers for fanout in fanouts)

    def writing(self, call: str, agent: str) -> Log:
        """The call's log for its writer, held until the process forgets the call."""
        log = self._log(call, agent)
        log.agent = agent
        if not log.kept_open:
            log.kept_open = True
            log.tap(self._feed)
        return log

    def reading(self, call: str) -> Log:
        """The call's log for a reader, whoever writes it."""
        self._prune(but=call)
        return self._log(call, "")

    def agent(self, slug: str) -> Log:
        """The agent's own log, for writing or reading."""
        self._prune(but=log_name(None, slug))
        log = self._log(None, slug)
        if not log.kept_open:
            log.kept_open = True
            log.tap(self._feed)
        return log

    def opened(self, call: str) -> Log | None:
        """The call's log if this process writes it."""
        log = self._logs.get(call)
        return log if log is not None and log.kept_open else None

    def forget(self, call: str) -> None:
        """Drop the call's log, its readers and its cached owner."""
        self._logs.pop(call, None)
        self._owners.pop(call, None)

    async def close(self) -> None:
        """Stop following every log."""
        await self.relay.close()

    def feed(self, org: str, env: Env) -> Fanout:
        """The org's feed in that env: the lifecycle entries of every log it owns there."""
        self._prune()
        feed = self._feeds.get((org, env))
        if feed is None:
            feed = self._feeds[(org, env)] = Fanout()
        return feed

    # Followed before it is subscribed, as a log's stream is: what any gateway writes from now on.
    async def feed_reader(self, org: str, env: Env) -> Subscription:
        """A reader of the org's feed in that env, hearing every gateway."""
        channel = FEED_CHANNEL.format(org=org, env=env.value)
        await self.relay.follow(channel, ordered=False)
        return self.feed(org, env).subscribe(after=lambda: self.relay.unfollow(channel))

    async def box_reader(self) -> Subscription:
        """A reader of every org's feed, hearing every gateway."""
        await self.relay.follow(BOX_CHANNEL, ordered=False)
        return self.box.subscribe(after=lambda: self.relay.unfollow(BOX_CHANNEL))

    # A change no log holds (a run, a release): its type and ids go to every gateway's readers of
    # the org's feed in that env and are kept nowhere, so a reader asks the endpoint for the rest.
    def announce(self, scope: Scope, kind: str, event: WireModel) -> None:
        """Say on the org's feed, in the scope's env, that something changed."""
        self.relay.local(FEED_CHANNEL.format(org=scope.org, env=scope.env.value), news(kind, event))

    def announce_to_the_box(self, kind: str, event: WireModel) -> None:
        """Say on the box's feed that something changed (a worker, say)."""
        self.relay.local(BOX_CHANNEL, news(kind, event))

    # What wakes a reader of the metered rows: a row written on any gateway, said as it is, after
    # it is stored. The reader reads the rows from its cursor; the entry is only the news.
    async def metered_reader(self) -> Subscription:
        """A reader that hears each metered entry written on any gateway from now on."""
        await self.relay.follow(USAGE_CHANNEL, ordered=False)
        return self.metered.subscribe(after=lambda: self.relay.unfollow(USAGE_CHANNEL))

    # Only a found owner is cached: a log nobody claimed yet may be claimed later.
    async def claimant_of(self, entry: Entry) -> Claimant | None:
        """Whose the entry's log is and in which env, asked of the store once per log."""
        name = log_name(entry.call, entry.agent)
        found = self._owners.get(name)
        if found is None:
            found = await self.store.claimant(entry.call, entry.agent)
            if found is not None:
                self._owners[name] = found
        return found

    def _log(self, call: str | None, agent: str) -> Log:
        name = log_name(call, agent)
        log = self._logs.get(name)
        if log is None:
            log = self._logs[name] = Log(self.store, call, agent, self.relay)
        return log

    # What the relay hands on, this process's own appends included: a log's readers hear it, and
    # the terminal entry ends them, sealed here or on another gateway; a feed's hear it as it came.
    def _deliver(self, channel: str, entry: Entry) -> None:
        fanout = self._fanout_of(channel)
        if fanout is None:
            return
        fanout.publish(entry)
        log = self._logs.get(log_name(entry.call, entry.agent))
        if entry.type == TERMINAL_EVENT and log is not None and fanout is log.fanout:
            log.sealed = log.call is not None
            if log.sealed:
                fanout.close()

    def _drop(self, channel: str) -> None:
        fanout = self._fanout_of(channel)
        if fanout is not None:
            fanout.drop()

    def _fanout_of(self, channel: str) -> Fanout | None:
        if channel == BOX_CHANNEL:
            return self.box
        if channel == USAGE_CHANNEL:
            return self.metered
        if channel.startswith(FEED_PREFIX):
            org, _, env = channel.removeprefix(FEED_PREFIX).rpartition(":")
            return self._feeds.get((org, Env(env)))
        log = self._logs.get(channel.removeprefix(LOG_PREFIX))
        return None if log is None else log.fanout

    # An agent's own entries serve both envs, so they reach the org's feed in each.
    async def _feed(self, entry: Entry) -> None:
        if entry.type in METERED_TYPES:
            self.relay.local(USAGE_CHANNEL, entry.model_copy(update={"data": {}}))
        if entry.type == "tool.result":
            await self._announce_tool(entry)
        if entry.type not in ORG_EVENTS:
            return
        claimant = await self.claimant_of(entry)
        if claimant is None:
            return
        if entry.type in ONLY_THAT_IT_HAPPENED:
            entry = entry.model_copy(update={"data": {}})
        self.relay.local(BOX_CHANNEL, entry)
        envs = tuple(Env) if claimant.env is None else (claimant.env,)
        for env in envs:
            self.relay.local(FEED_CHANNEL.format(org=claimant.org, env=env.value), entry)

    # Every tool.result passes here, whichever gateway or worker wrote it: said with the tool's name and
    # seconds, never its error, arguments or output, which are the call's content.
    async def _announce_tool(self, entry: Entry) -> None:
        claimant = await self.claimant_of(entry)
        try:
            result = ToolResult.parse(entry.data, entry.type)
        except ValidationError:
            return
        if claimant is None or claimant.env is None or entry.call is None:
            return
        scope = Scope(claimant.org, claimant.env)
        if result.error is None:
            ran = ToolRan(call=entry.call, agent=entry.agent, name=result.name, duration_s=result.duration_s)
            self.announce(scope, "tool.ran", ran)
        else:
            failed = ToolFailed(call=entry.call, agent=entry.agent, name=result.name, duration_s=result.duration_s)
            self.announce(scope, "tool.failed", failed)

    # On every read, so readers asking for arbitrary names cannot grow the tables without bound.
    def _prune(self, *, but: str = "") -> None:
        idle = [
            name for name, log in self._logs.items() if name != but and not log.kept_open and not log.fanout.readers
        ]
        for name in idle:
            del self._logs[name]
        for key in [k for k, feed in self._feeds.items() if not feed.readers]:
            del self._feeds[key]


# What a feed says of a change no log holds: its type and ids, the moment it is said, kept nowhere.
def news(kind: str, event: WireModel) -> Entry:
    """An entry of the feed for something that changed, said once and never stored."""
    return Entry(seq=0, ts=time.time(), call=None, agent="", type=kind, ephemeral=True, data=event.dump())
