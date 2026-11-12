"""The relay: what any gateway wrote, handed to whoever hears a log or a feed in this process, a log's in seq order."""

import asyncio
import json
from dataclasses import dataclass, field
from typing import Protocol
from uuid import uuid4

from runtime.calls.context import log_name
from runtime.calls.log.fanout import Subscription
from runtime.calls.log.store import Store
from runtime.calls.repository.entries import A_PAGE
from runtime.enums import Env
from runtime.exceptions import ServiceUnavailable
from runtime.kit.loops import survive
from runtime.scoping import box_task
from runtime.signal import Listener, Signal
from runtime.wire.base import Entry
from runtime.wire.signal import Travelled

# The box's feed and the one that wakes the readers of the metered rows. Followed without a
# sequencer, as an org's feed is: a feed spans calls and is live-only, each entry carrying its log
# and seq for a reader that needs a call's order.
BOX_CHANNEL = "box"
USAGE_CHANNEL = "usage"

# A durable entry over this many bytes travels as its address, and the hearer reads it back.
STUB_OVER_BYTES = 64 * 1024

# How long an entry that arrived ahead of its turn waits for the ones before it, before the
# store is asked for them; and how often the store is asked for every followed log while the
# signal is down, when durable entries still arrive and ephemerals do not.
FILL_AFTER_S = 0.1
POLL_S = 1.0


# Each log has a channel of its own, so a gateway hears only the logs something local reads. The
# names are what the gateways of the release before this one publish on and listen to.
def log_channel(log: str) -> str:
    """The channel a log's entries are told on."""
    return f"log:{log}"


def feed_channel(org: str, env: Env) -> str:
    """The channel of an org's feed in one env."""
    return f"feed:{org}:{env.value}"


# Whoever the relay hands a channel's entries to: a feed's fanout as it is, a log, which ends its
# readers at the entry that ends its call.
class Hearer(Protocol):
    """What hears a channel in this process."""

    def publish(self, entry: Entry) -> None:
        """One entry of the channel, in its turn."""
        ...

    def drop(self) -> None:
        """The channel was lost: every reader resumes from the store."""
        ...


@dataclass
class Following:
    """One channel this process follows: who hears it, the last seq handed on, what came early."""

    channel: str
    # The log a channel of seq order belongs to, read back from the store where a seq is missing;
    # None for a feed, handed on as it comes.
    log: str | None = None
    # Each hearer, and how many of its readers follow.
    hearers: dict[Hearer, int] = field(default_factory=dict[Hearer, int])
    last: int = 0
    held: dict[int, Entry] = field(default_factory=dict[int, Entry])
    # Set once the subscription is confirmed, or once the store is polled instead.
    ready: asyncio.Event = field(default_factory=asyncio.Event)
    listener: Listener | None = None
    task: asyncio.Task[None] | None = None
    filling: asyncio.Task[None] | None = None
    closed: bool = False


# Stored before published, and every hearer resumes from the store: a message may be lost, or
# arrive out of turn, and what a reader is given is still whole and in seq order.
class Relay:
    """Follows the channels something local reads, and hands each entry on once, a log's in its turn."""

    def __init__(self, signal: Signal, store: Store) -> None:
        """Tell and hear on the signal; read from the store what the signal lost or sent as an address."""
        self.signal = signal
        # Several relays may share one in-process signal: each skips only what it sent itself.
        self.id = uuid4().hex
        self._store = store
        self._following: dict[str, Following] = {}

    @property
    def followed(self) -> int:
        """How many channels this process follows now."""
        return len(self._following)

    async def follow_log(self, log: str, hearer: Hearer, reader: Subscription) -> Subscription:
        """The reader, once the log's channel is followed for it and its entries reach the hearer in seq order."""
        return await self._follow(log_channel(log), log, hearer, reader)

    async def follow_feed(self, channel: str, hearer: Hearer, reader: Subscription) -> Subscription:
        """The reader, once the feed's channel is followed for it and its entries reach the hearer as they come."""
        return await self._follow(channel, None, hearer, reader)

    def unfollow(self, channel: str, hearer: Hearer) -> None:
        """One reader of the hearer left the channel; the last one leaving lets the channel go."""
        following = self._following.get(channel)
        if following is None or hearer not in following.hearers:
            return
        following.hearers[hearer] -= 1
        if following.hearers[hearer] <= 0:
            del following.hearers[hearer]
        if not following.hearers:
            self._let_go(following)

    def tell(self, channel: str, entry: Entry) -> None:
        """An entry this process wrote: told to every gateway, and handed on here in its turn."""
        self.signal.publish(channel, encode(entry, self.id))
        following = self._following.get(channel)
        if following is None:
            return
        if following.log is None or not following.ready.is_set():
            self._hand(following, entry)
        else:
            self._sequence(following, entry)

    async def close(self) -> None:
        """Let every channel go and wait for their tasks."""
        followings = list(self._following.values())
        for following in followings:
            self._let_go(following)
        tasks = [following.task for following in followings if following.task is not None]
        await asyncio.gather(*tasks, return_exceptions=True)

    # A reader is subscribed before its follow, so no prune drops what it reads while the signal
    # confirms; one whose follow fails (the request gone meanwhile) is closed, which lets the channel
    # go again. A reader that is over already (its fanout was closed before it entered) follows
    # nothing: nobody would ever let that channel go.
    async def _follow(self, channel: str, log: str | None, hearer: Hearer, reader: Subscription) -> Subscription:
        if reader.over:
            return reader
        following = self._following.get(channel)
        if following is None:
            following = self._following[channel] = Following(channel, log)
            following.task = box_task(self._run(following))
        following.hearers[hearer] = following.hearers.get(hearer, 0) + 1
        try:
            await following.ready.wait()
        except BaseException:
            reader.close()
            raise
        return reader

    async def _run(self, following: Following) -> None:
        try:
            listener = await self.signal.subscribe(following.channel)
        except ServiceUnavailable:
            listener = None
        if following.log is not None:
            following.last = await self._store.seq_of(following.log)
        following.listener = listener
        following.ready.set()
        if following.closed:
            if listener is not None:
                listener.close()
            return
        if listener is None:
            await self._poll(following)
            return
        async for data in listener:
            # One message that cannot be applied is said with its channel: an entry it carried that
            # the store has is filled in when the next one arrives, and the readers are not left deaf.
            with survive("following a log", following.channel):
                await self._hear(following, data)
        self._lose(following)

    # The signal is down: a log's durable entries are read off the store each second (a feed
    # spans calls and cannot be, so its readers hear this process alone), until it is back, when
    # the readers are told to resume so the channel is followed again.
    async def _poll(self, following: Following) -> None:
        while not following.closed:
            await asyncio.sleep(POLL_S)
            if following.closed:
                return
            if following.log is not None:
                with survive("reading a log off the store while the signal is down", following.channel):
                    for entry in await self._store.page_of(following.log, after=following.last, limit=A_PAGE):
                        if entry.seq > following.last:
                            self._hand_next(following, entry)
            if self.signal.up:
                self._lose(following)
                return

    async def _hear(self, following: Following, data: bytes) -> None:
        travelled = Travelled.model_validate_json(data)
        if travelled.sender == self.id:
            return
        if travelled.entry is not None:
            self._take(following, travelled.entry)
        elif travelled.stored is not None:
            seq = travelled.stored.seq
            found = await self._store.page_of(travelled.stored.log, after=seq - 1, limit=1)
            if found and found[0].seq == seq:
                self._take(following, found[0])

    def _take(self, following: Following, entry: Entry) -> None:
        if following.log is not None:
            self._sequence(following, entry)
        elif not following.closed:
            self._hand(following, entry)

    def _sequence(self, following: Following, entry: Entry) -> None:
        if following.closed or entry.seq <= following.last:
            return
        if entry.seq == following.last + 1:
            self._hand_next(following, entry)
            while (queued := following.held.pop(following.last + 1, None)) is not None:
                self._hand_next(following, queued)
            return
        following.held[entry.seq] = entry
        if following.filling is None:
            following.filling = box_task(self._fill(following))

    # What is missing before the held ones is read from the store: by the head's lock every
    # durable entry below a seq given out is committed, so a seq not found is an ephemeral, lost.
    async def _fill(self, following: Following) -> None:
        await asyncio.sleep(FILL_AFTER_S)
        try:
            with survive("filling a log's gap", following.channel):
                if following.closed or not following.held or following.log is None:
                    return
                highest = max(following.held)
                wanted = highest - following.last
                for entry in await self._store.page_of(following.log, after=following.last, limit=wanted):
                    if following.last < entry.seq <= highest:
                        following.held.setdefault(entry.seq, entry)
                for seq in sorted(seq for seq in following.held if seq <= highest):
                    entry = following.held.pop(seq)
                    if seq > following.last:
                        self._hand_next(following, entry)
        finally:
            following.filling = None
            if following.held and not following.closed:
                following.filling = box_task(self._fill(following))

    # The channel was lost: this following is over, so a reader that comes back follows a new
    # one (subscribed again) rather than this one, which nobody listens on; its readers are dropped.
    def _lose(self, following: Following) -> None:
        if following.closed:
            return
        following.closed = True
        if self._following.get(following.channel) is following:
            del self._following[following.channel]
        for hearer in tuple(following.hearers):
            hearer.drop()

    def _hand_next(self, following: Following, entry: Entry) -> None:
        following.last = entry.seq
        self._hand(following, entry)

    def _hand(self, following: Following, entry: Entry) -> None:
        for hearer in tuple(following.hearers):
            hearer.publish(entry)

    def _let_go(self, following: Following) -> None:
        following.closed = True
        self._following.pop(following.channel, None)
        if following.listener is not None:
            following.listener.close()
        if following.filling is not None:
            following.filling.cancel()
        if following.task is not None and following.task is not asyncio.current_task():
            following.task.cancel()


# A big entry's address names its own log, which a feed's channel does not.
def encode(entry: Entry, sender: str) -> bytes:
    """The message an entry travels as: itself, or its address when it is big and durable."""
    whole = f'{{"sender":{json.dumps(sender)},"entry":{entry.dump_json()}}}'
    if len(whole) > STUB_OVER_BYTES and not entry.ephemeral:
        stub = {"sender": sender, "stored": {"log": log_name(entry.call, entry.agent), "seq": entry.seq}}
        return json.dumps(stub, separators=(",", ":")).encode()
    return whole.encode()
