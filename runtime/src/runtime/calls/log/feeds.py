"""The feeds: an org's in each env, the box's, the one that wakes the usage's readers, and what they say of a call."""

from collections import OrderedDict
from dataclasses import dataclass

from runtime.actor import Scope
from runtime.calls.context import log_name
from runtime.calls.log.fanout import Fanout, Subscription
from runtime.calls.log.relay import BOX_CHANNEL, USAGE_CHANNEL, Relay, feed_channel
from runtime.calls.log.store import Clock, Store
from runtime.calls.log.writer import METERED_TYPES
from runtime.calls.repository.heads import Claimant
from runtime.enums import Env
from runtime.exceptions import ValidationError
from runtime.wire.base import Entry, WireModel
from runtime.wire.feed import ToolFailed, ToolRan
from runtime.wire.parts import ToolResult

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

# How many logs' owners a gateway remembers. A log's owner never changes, so the cache is only
# ever right; it is bounded because the box's feed asks for the owner of every call of every org,
# and nothing ever forgot the ones this gateway did not serve.
OWNERS_REMEMBERED = 4096


@dataclass(frozen=True, slots=True)
class News:
    """What a feed says of a change no log holds: where, its kind, and the event."""

    scope: Scope
    kind: str
    event: WireModel


def feed_entry_of(entry: Entry) -> Entry | None:
    """The entry as the feeds carry it, or None for one they do not: the lifecycle alone, its content left out."""
    if entry.type not in ORG_EVENTS:
        return None
    return entry.model_copy(update={"data": {}}) if entry.type in ONLY_THAT_IT_HAPPENED else entry


# An agent's own entries serve both envs, so they reach the org's feed in each.
def feed_channels(claimant: Claimant) -> tuple[str, ...]:
    """The box's channel and the claimant's org's, in each env the entry serves."""
    envs = tuple(Env) if claimant.env is None else (claimant.env,)
    return (BOX_CHANNEL, *(feed_channel(claimant.org, env) for env in envs))


# Said with the tool's name and seconds, never its error, arguments or output, which are the call's content.
def tool_news(entry: Entry, claimant: Claimant) -> News | None:
    """What the org's feed says of a tool.result: where, the kind (`tool.ran`, `tool.failed`) and the event."""
    try:
        result = ToolResult.parse(entry.data, entry.type)
    except ValidationError:
        return None
    if claimant.env is None or entry.call is None:
        return None
    scope = Scope(claimant.org, claimant.env)
    kind, event = ("tool.ran", ToolRan) if result.error is None else ("tool.failed", ToolFailed)
    said = event(call=entry.call, agent=entry.agent, name=result.name, duration_s=result.duration_s)
    return News(scope, kind, said)


# What a feed says of a change no log holds: its type and ids, the moment it is said, kept nowhere.
def news(kind: str, event: WireModel, at: float) -> Entry:
    """An entry of the feed for something that changed, said once and never stored."""
    return Entry(seq=0, ts=at, call=None, agent="", type=kind, ephemeral=True, data=event.dump())


# Live only: a feed spans calls and keeps nothing, so a reader that needs what it missed asks the
# endpoint that lists it.
class Feeds:
    """Every feed of this process: its readers, what each is told, and whose every log is."""

    def __init__(self, relay: Relay, store: Store) -> None:
        """Start with no feed listened to."""
        self.box = Fanout()
        self.metered = Fanout()
        self._relay = relay
        self._store = store
        self._clock: Clock = store.clock
        self._orgs: dict[tuple[str, Env], Fanout] = {}
        # A log's owner never changes; caching it keeps a store read off the append path.
        self._owners: OrderedDict[str, Claimant] = OrderedDict()

    @property
    def readers(self) -> int:
        """How many live readers the feeds of this process hold."""
        return sum(fanout.readers for fanout in (self.box, self.metered, *self._orgs.values()))

    # Subscribed, then followed, as a log's stream is: what any gateway writes from now on.
    async def reader_of(self, org: str, env: Env) -> Subscription:
        """A reader of the org's feed in that env: the lifecycle entries of every log it owns there."""
        channel = feed_channel(org, env)
        feed = self._feed_of(org, env)
        reader = feed.subscribe(after=lambda: self._relay.unfollow(channel, feed))
        return await self._relay.follow_feed(channel, feed, reader)

    async def box_reader(self) -> Subscription:
        """A reader of every org's feed, hearing every gateway."""
        reader = self.box.subscribe(after=lambda: self._relay.unfollow(BOX_CHANNEL, self.box))
        return await self._relay.follow_feed(BOX_CHANNEL, self.box, reader)

    # What wakes a reader of the metered rows: a row written on any gateway, said as it is, after
    # it is stored. The reader reads the rows from its cursor; the entry is only the news.
    async def usage_reader(self) -> Subscription:
        """A reader that hears each metered entry written on any gateway from now on."""
        reader = self.metered.subscribe(after=lambda: self._relay.unfollow(USAGE_CHANNEL, self.metered))
        return await self._relay.follow_feed(USAGE_CHANNEL, self.metered, reader)

    # A change no log holds (a run, a release): its type and ids go to every gateway's readers of
    # the org's feed in that env and are kept nowhere, so a reader asks the endpoint for the rest.
    def announce(self, scope: Scope, kind: str, event: WireModel) -> None:
        """Say on the org's feed, in the scope's env, that something changed."""
        self._relay.tell(feed_channel(scope.org, scope.env), news(kind, event, self._clock()))

    def announce_to_the_box(self, kind: str, event: WireModel) -> None:
        """Say on the box's feed that something changed (a worker, say)."""
        self._relay.tell(BOX_CHANNEL, news(kind, event, self._clock()))

    # Only a found owner is cached: a log nobody claimed yet may be claimed later.
    async def claimant_of(self, entry: Entry) -> Claimant | None:
        """Whose the entry's log is and in which env, asked of the store once per log."""
        name = log_name(entry.call, entry.agent)
        found = self._owners.get(name)
        if found is not None:
            self._owners.move_to_end(name)
            return found
        found = await self._store.claimant_of(entry.call, entry.agent)
        if found is not None:
            self._owners[name] = found
            if len(self._owners) > OWNERS_REMEMBERED:
                self._owners.popitem(last=False)
        return found

    # The tap of every log this process writes: runs on each entry after it is stored and told.
    async def carry(self, entry: Entry) -> None:
        """Say what the feeds say of an entry written here: the usage's news, a tool's, the lifecycle."""
        if entry.type in METERED_TYPES:
            self._relay.tell(USAGE_CHANNEL, entry.model_copy(update={"data": {}}))
        # Every tool.result passes here, whichever gateway or worker wrote it.
        if entry.type == "tool.result":
            await self._announce_tool(entry)
        carried = feed_entry_of(entry)
        if carried is None:
            return
        claimant = await self.claimant_of(entry)
        if claimant is not None:
            for channel in feed_channels(claimant):
                self._relay.tell(channel, carried)

    def forget(self, log: str) -> None:
        """Drop the log's cached owner."""
        self._owners.pop(log, None)

    async def _announce_tool(self, entry: Entry) -> None:
        claimant = await self.claimant_of(entry)
        said = None if claimant is None else tool_news(entry, claimant)
        if said is not None:
            self.announce(said.scope, said.kind, said.event)

    # On every ask, so readers asking for arbitrary orgs cannot grow the table without bound.
    def _feed_of(self, org: str, env: Env) -> Fanout:
        for key in [key for key, feed in self._orgs.items() if not feed.readers]:
            del self._orgs[key]
        feed = self._orgs.get((org, env))
        if feed is None:
            feed = self._orgs[(org, env)] = Fanout()
        return feed
