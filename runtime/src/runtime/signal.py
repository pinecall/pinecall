"""The signal between gateways: what they tell each other on, a listener of it, and the one inside a process."""

import asyncio
from collections import deque
from collections.abc import Callable
from typing import Protocol, Self
from uuid import uuid4

# How far a listener may fall behind before it is dropped.
LISTENING_DEPTH = 256

DOWN = "the live signal between gateways is down: no Redis answers at PINECALL_REDIS_URL"


class Listener:
    """One listener of one channel, in order; ended when closed, dropped when it fell behind."""

    def __init__(self, channel: str, leave: Callable[["Listener"], None]) -> None:
        self.channel = channel
        # True when it fell behind or its connection was lost: what it missed is the store's.
        self.dropped = False
        self._leave = leave
        self._heard: deque[bytes] = deque()
        self._moved = asyncio.Event()
        self._over = False

    def offer(self, data: bytes) -> bool:
        """Queue the message; False once the listener is over or fell behind."""
        if self._over:
            return False
        if len(self._heard) >= LISTENING_DEPTH:
            self.drop()
            return False
        self._heard.append(data)
        self._moved.set()
        return True

    def drop(self) -> None:
        """End it as cut off, after what it was already given."""
        self.dropped = True
        self._finish()

    def close(self) -> None:
        """End it after what it was already given, and stop listening."""
        self._finish()
        self._leave(self)

    def _finish(self) -> None:
        self._over = True
        self._moved.set()

    def __aiter__(self) -> Self:
        return self

    async def __anext__(self) -> bytes:
        while not self._heard:
            if self._over:
                raise StopAsyncIteration
            self._moved.clear()
            await self._moved.wait()
        return self._heard.popleft()


class Signal(Protocol):
    """What the gateways tell each other on: fire-and-forget publish, ordered per-channel listen."""

    id: str

    @property
    def up(self) -> bool:
        """Whether the listening connection is subscribed now."""
        ...

    async def wait_until_up(self) -> None:
        """Return once connected; at once when it is."""
        ...

    def publish(self, channel: str, data: bytes) -> None:
        """Queue the message for every listener of the channel; never waits."""
        ...

    async def publish_now(self, channel: str, data: bytes) -> int:
        """Publish now and answer how many listeners there were; ServiceUnavailable while down."""
        ...

    async def subscribe(self, channel: str) -> Listener:
        """A listener of what is published on the channel from now on."""
        ...

    async def close(self) -> None:
        """End every listener and the connections."""
        ...


class LocalSignal:
    """The signal inside one process: a gateway alone, with no PINECALL_REDIS_URL."""

    def __init__(self) -> None:
        self.id = f"gw_{uuid4().hex[:12]}"
        self._listening: dict[str, set[Listener]] = {}

    @property
    def up(self) -> bool:
        """Always."""
        return True

    async def wait_until_up(self) -> None:
        """At once."""

    def publish(self, channel: str, data: bytes) -> None:
        """Hand the message to every listener."""
        for listener in tuple(self._listening.get(channel, ())):
            if not listener.offer(data):
                self._leave(listener)

    async def publish_now(self, channel: str, data: bytes) -> int:
        """Hand the message to every listener; how many there were."""
        heard = len(self._listening.get(channel, ()))
        self.publish(channel, data)
        return heard

    async def subscribe(self, channel: str) -> Listener:
        """A listener of the channel."""
        listener = Listener(channel, self._leave)
        self._listening.setdefault(channel, set()).add(listener)
        return listener

    async def close(self) -> None:
        """End every listener."""
        for listeners in list(self._listening.values()):
            for listener in tuple(listeners):
                listener.close()

    def _leave(self, listener: Listener) -> None:
        listeners = self._listening.get(listener.channel, set())
        listeners.discard(listener)
        if not listeners:
            self._listening.pop(listener.channel, None)
