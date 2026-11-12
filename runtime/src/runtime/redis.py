"""The signal on Redis: one connection publishes, one listens, both come back; and how a process opens its signal."""

import asyncio
import logging
from collections import deque
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from uuid import uuid4

from redis.asyncio import Redis
from redis.asyncio.client import PubSub
from redis.asyncio.retry import Retry
from redis.backoff import NoBackoff
from redis.exceptions import ConnectionError as RedisConnectionError
from redis.exceptions import RedisError

from runtime.config import Settings
from runtime.exceptions import ConfigurationError, ServiceUnavailable
from runtime.kit.loops import survive
from runtime.scoping import box_task
from runtime.signal import Listener, LocalSignal, Signal

logger = logging.getLogger(__name__)

# LiveKit shares the Redis, and a channel's name is global to it.
PREFIX = "pinecall:"

# How many messages wait for Redis before the oldest goes; how many go in one pipeline.
UNSENT_AT_MOST = 10_000
MOST_A_PIPELINE = 512

ANSWER_S = 2.0
PING_S = 5.0
SILENT_AT_MOST_S = 15.0
TICK_S = 1.0
FIRST_PAUSE_S = 0.5
LONGEST_PAUSE_S = 5.0


@dataclass(frozen=True, slots=True)
class _Heard:
    kind: str
    channel: str | None
    data: bytes | None


# Lossy on purpose: a message published while Redis is away, or to a listener that fell behind, is
# gone, and whoever listened resumes from the store. redis-py retries nothing here (its PubSub
# would resubscribe behind our back and hide what was missed): the reconnection is ours.
class RedisSignal:
    """The signal on Redis: one connection publishes in pipelines, one listens; both come back."""

    # The two connections are handed in: `at` makes them for a URL, as a process opens its signal.
    def __init__(self, client: Redis, listener: Redis, *, gateway: str, prefix: str = PREFIX) -> None:
        self.id = gateway
        self.prefix = prefix
        self._up = False
        self._connected = asyncio.Event()
        self.dropped = 0
        self._client = client
        self._listener = listener
        self._unsent: deque[tuple[str, bytes]] = deque()
        self._waiting = asyncio.Event()
        self._listening: dict[str, set[Listener]] = {}
        self._confirmed: dict[str, asyncio.Future[bool]] = {}
        self._leaving: set[str] = set()
        self._pubsub: PubSub | None = None
        self._reconnected = False
        self._tasks: list[asyncio.Task[None]] = []

    @classmethod
    def at(cls, url: str, *, prefix: str = PREFIX) -> "RedisSignal":
        """The signal on the Redis at this URL: a gateway of its own, each connection named after it."""
        gateway = new_gateway_id()
        return cls(_client_of(url, gateway), _client_of(url, gateway), gateway=gateway, prefix=prefix)

    @property
    def up(self) -> bool:
        """Whether the listening connection is subscribed now."""
        return self._up

    async def wait_until_up(self) -> None:
        """Return once the listening connection is subscribed."""
        await self._connected.wait()

    def start(self) -> None:
        """Start sending and listening; a Redis that is away is waited for."""
        self._tasks = [box_task(self._sending()), box_task(self._listen())]

    async def publish_now(self, channel: str, data: bytes) -> int:
        """Publish now; how many listeners Redis handed it to."""
        try:
            async with asyncio.timeout(ANSWER_S):
                heard = await self._client.publish(self.prefix + channel, data)  # pyright: ignore[reportUnknownMemberType]
        except (RedisError, OSError, TimeoutError) as away:
            raise ServiceUnavailable(
                "the live signal between gateways is down: no Redis answers at PINECALL_REDIS_URL"
            ) from away
        return int(heard)

    def publish(self, channel: str, data: bytes) -> None:
        """Queue the message; never waits for Redis."""
        if len(self._unsent) >= UNSENT_AT_MOST:
            self._unsent.popleft()
            self.dropped += 1
        self._unsent.append((self.prefix + channel, data))
        self._waiting.set()

    async def subscribe(self, channel: str) -> Listener:
        """A listener, returned once Redis confirmed the subscription."""
        pubsub = self._pubsub
        if not self._up or pubsub is None:
            raise ServiceUnavailable("the live signal between gateways is down: no Redis answers at PINECALL_REDIS_URL")
        name = self.prefix + channel
        listener = Listener(channel, self._leave)
        self._listening.setdefault(name, set()).add(listener)
        confirmed = self._confirmed.get(name)
        try:
            if confirmed is None:
                confirmed = self._confirmed[name] = asyncio.get_running_loop().create_future()
                await pubsub.subscribe(name)  # pyright: ignore[reportUnknownMemberType]
            async with asyncio.timeout(ANSWER_S):
                is_confirmed = await asyncio.shield(confirmed)
        except (RedisError, OSError, TimeoutError):
            is_confirmed = False
        except asyncio.CancelledError:
            listener.close()
            raise
        if not is_confirmed:
            listener.close()
            raise ServiceUnavailable("the live signal between gateways is down: no Redis answers at PINECALL_REDIS_URL")
        return listener

    async def close(self) -> None:
        """Stop both connections; every listener ends, what was not sent is dropped."""
        for task in self._tasks:
            task.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)
        for listeners in list(self._listening.values()):
            for listener in tuple(listeners):
                listener.close()
        await self._forget_the_connection()
        await self._client.aclose()
        await self._listener.aclose()

    async def _sending(self) -> None:
        pause = 0.0
        while True:
            await self._waiting.wait()
            self._waiting.clear()
            while self._unsent:
                taken = min(len(self._unsent), MOST_A_PIPELINE)
                batch = [self._unsent.popleft() for _ in range(taken)]
                try:
                    async with self._client.pipeline(transaction=False) as pipe:
                        for name, data in batch:
                            pipe.publish(name, data)  # pyright: ignore[reportUnknownMemberType]
                        await pipe.execute()
                    pause = 0.0
                except Exception:
                    # Whatever it was, not only Redis being away: a sender that ended would drop
                    # every message of the box for good, and nothing else would say so.
                    self.dropped += len(batch)
                    if not pause:
                        logger.warning("the signal cannot publish to Redis; dropping", exc_info=True)
                    pause = _longer(pause)
                    await asyncio.sleep(pause)

    async def _listen(self) -> None:
        pause = 0.0
        while True:
            try:
                await self._hear()
            except Exception:
                # Redis lost, or anything else a message made this raise: either way the listeners
                # resume from the store, and the loop that listens is not the thing that ends.
                if not pause:
                    logger.warning("the signal lost Redis; listeners resume from the store", exc_info=True)
            pause = 0.0 if self._up else _longer(pause)
            with survive("the signal's letting go of its connection"):
                await self._on_loss()
            await asyncio.sleep(pause)

    async def _hear(self) -> None:
        pubsub = self._pubsub = self._listener.pubsub()  # pyright: ignore[reportUnknownMemberType]
        own = f"{self.prefix}signal:{self.id}"
        await pubsub.subscribe(own)  # pyright: ignore[reportUnknownMemberType]
        self._reconnected = False
        if pubsub.connection is not None:
            pubsub.connection.register_connect_callback(self._on_reconnect)  # pyright: ignore[reportUnknownMemberType]
        clock = asyncio.get_running_loop().time
        heard_at = pinged_at = clock()
        while True:
            heard = _message_of(await _next_message(pubsub))
            now = clock()
            if heard is not None:
                heard_at = now
                self._handle(heard, own)
            if now - heard_at > SILENT_AT_MOST_S:
                raise RedisConnectionError(f"Redis said nothing for {now - heard_at:.0f} s")
            if self._reconnected:
                raise RedisConnectionError("the client reconnected behind our back")
            if now - pinged_at >= PING_S:
                pinged_at = now
                await pubsub.execute_command("PING")
            leaving, self._leaving = self._leaving, set()
            for name in leaving - self._listening.keys():
                await pubsub.execute_command("UNSUBSCRIBE", name)

    def _on_reconnect(self, _connection: object) -> None:
        self._reconnected = True

    def _handle(self, heard: _Heard, own: str) -> None:
        if heard.kind == "subscribe" and heard.channel is not None:
            if heard.channel == own:
                self._up = True
                self._connected.set()
            confirmed = self._confirmed.get(heard.channel)
            if confirmed is not None and not confirmed.done():
                confirmed.set_result(True)
            return
        if heard.kind != "message" or heard.channel is None or heard.data is None:
            return
        for listener in tuple(self._listening.get(heard.channel, ())):
            if not listener.offer(heard.data):
                self._leave(listener)

    async def _on_loss(self) -> None:
        self._up = False
        self._connected.clear()
        listening, self._listening = self._listening, {}
        confirmed, self._confirmed = self._confirmed, {}
        self._leaving.clear()
        for waiting in confirmed.values():
            if not waiting.done():
                waiting.set_result(False)
        for listeners in listening.values():
            for listener in listeners:
                listener.drop()
        await self._forget_the_connection()

    async def _forget_the_connection(self) -> None:
        pubsub, self._pubsub = self._pubsub, None
        if pubsub is not None:
            await pubsub.aclose()

    def _leave(self, listener: Listener) -> None:
        name = self.prefix + listener.channel
        listeners = self._listening.get(name)
        if listeners is None or listener not in listeners:
            return
        listeners.discard(listener)
        if not listeners:
            del self._listening[name]
            self._confirmed.pop(name, None)
            self._leaving.add(name)


def new_gateway_id() -> str:
    """A gateway's id on the signal, its own for its life."""
    return f"gw_{uuid4().hex[:12]}"


def _client_of(url: str, name: str) -> Redis:
    try:
        client: Redis = Redis.from_url(  # pyright: ignore[reportUnknownMemberType]
            url,
            retry=Retry(NoBackoff(), 0),
            socket_connect_timeout=ANSWER_S,
            socket_timeout=ANSWER_S,
            client_name=f"pinecall-{name}",
        )
        return client
    except ValueError as wrong:
        raise ConfigurationError(f"PINECALL_REDIS_URL is not a Redis URL ({wrong})") from None


# redis-py answers an untyped dict: it is read as an object, and matched by its shape.
async def _next_message(pubsub: PubSub) -> object:
    return await pubsub.get_message(timeout=TICK_S)  # pyright: ignore[reportUnknownVariableType]


def _message_of(message: object) -> _Heard | None:
    match message:
        case {"type": str() as kind, "channel": object() as channel, "data": object() as data}:
            name = channel.decode() if isinstance(channel, bytes) else None
            return _Heard(kind, name, data if isinstance(data, bytes) else None)
        case _:
            return None


def _longer(pause: float) -> float:
    return FIRST_PAUSE_S if not pause else min(pause * 2, LONGEST_PAUSE_S)


@asynccontextmanager
async def open_signal(settings: Settings) -> AsyncGenerator[Signal]:
    """Redis at PINECALL_REDIS_URL, or this process alone when unset; closed after."""
    signal: Signal
    if settings.redis_url is None:
        signal = LocalSignal()
    else:
        redis = RedisSignal.at(settings.redis_url.get_secret_value())
        redis.start()
        signal = redis
    try:
        yield signal
    finally:
        await signal.close()
