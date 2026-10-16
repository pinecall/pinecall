"""The gateway's socket: the key at the door, the way back after a drop, a ping, frames in order."""

import asyncio
import contextlib
import logging
import random
import threading
import time
from collections import deque
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from websockets.asyncio.client import ClientConnection, connect
from websockets.exceptions import ConnectionClosed, InvalidHandshake, InvalidStatus

from pinecall._endpoints import apps_url, signed
from pinecall.errors import NotConnected, WireError
from pinecall.wire._names import Env
from pinecall.wire.frames import Entry

# RFC 6455's policy violation: the gateway refused the key for this socket. Said, not retried:
# retrying a key that lacks the scope would loop quietly forever.
POLICY_VIOLATION = 1008

OPEN_WITHIN_S = 10.0

logger = logging.getLogger("pinecall")


@dataclass(frozen=True)
class Backoff:
    """How long to wait before dialling again: the first window, its ceiling, and its growth."""

    first_s: float = 0.5
    cap_s: float = 30.0
    factor: float = 2.0

    def wait_s(self, attempt: int) -> float:
        """Full jitter, so the clients that lost one gateway do not come back in lockstep."""
        return random.random() * min(self.cap_s, self.first_s * self.factor**attempt)  # noqa: S311 - a delay, not a secret


@dataclass(frozen=True)
class Handlers:
    """What a connection calls: on every open, every entry, every failure, every beat."""

    on_open: Callable[[], Awaitable[None]]
    on_entry: Callable[[Entry], None]
    on_error: Callable[[Exception], None]
    on_beat: Callable[[], None]


class Connection:
    """One gateway socket across its reconnects."""

    def __init__(
        self,
        url: str,
        signing: tuple[str, Env | None],
        handlers: Handlers,
        *,
        ping_s: float = 30.0,
        backoff: Backoff = Backoff(),  # noqa: B008 - frozen, so one default is shared safely
    ) -> None:
        """A connection to the gateway at `url`, signed with the key and the world."""
        self._url = apps_url(url)
        self._headers = signed(*signing)
        self._handlers = handlers
        self._ping_s = ping_s
        self._backoff = backoff
        self._socket: ClientConnection | None = None
        self._outbox: Outbox | None = None
        self._tasks: set[asyncio.Task[None]] = set()
        self._closed = False

    @property
    def open(self) -> bool:
        """Whether the socket is up now."""
        return self._socket is not None and self._outbox is not None

    async def start(self) -> None:
        """Dial and run `on_open`; a failure here is raised. Later drops are dialled again."""
        self._closed = False
        socket = await self._dial()
        self._spawn(self._kept(socket))

    def send(self, text: str) -> None:
        """Queue one frame; frames leave in the order they were sent, from any thread."""
        outbox = self._outbox
        if outbox is None:
            raise NotConnected("the gateway is not connected")
        outbox.put(text)

    def leaving(self) -> None:
        """Keep this socket and never dial again: a drain must not take back the calls it gave."""
        self._closed = True

    async def close(self) -> None:
        """Close the socket for good."""
        self._closed = True
        socket, self._socket, self._outbox = self._socket, None, None
        for task in list(self._tasks):
            task.cancel()
        if socket is not None:
            await socket.close()

    async def _dial(self) -> ClientConnection:
        try:
            socket = await connect(
                self._url,
                additional_headers=self._headers,
                open_timeout=OPEN_WITHIN_S,
                ping_interval=None,
                max_size=None,
            )
        except InvalidStatus as refused:
            said = refused.response.body.decode(errors="replace") if refused.response.body else ""
            raise NotConnected(
                f"the gateway refused the socket: {refused.response.status_code} {said}".strip()
            ) from refused
        except (OSError, InvalidHandshake, TimeoutError) as failed:
            raise NotConnected(f"the gateway is not reachable at {self._url}: {failed}") from failed
        self._socket, self._outbox = socket, Outbox(asyncio.get_running_loop())
        self._spawn(self._read(socket))
        self._spawn(self._write(socket, self._outbox))
        # The declaration waits for entries the reader hands over: it runs here, never there. A
        # socket the gateway closes meanwhile fails it at once, with the gateway's reason.
        declared = asyncio.ensure_future(self._handlers.on_open())
        dropped = asyncio.ensure_future(socket.wait_closed())
        await asyncio.wait({declared, dropped}, return_when=asyncio.FIRST_COMPLETED)
        dropped.cancel()
        if not declared.done():
            declared.cancel()
            raise NotConnected(
                f"the gateway closed the socket: {socket.close_reason or socket.close_code}"
            )
        try:
            declared.result()
        except BaseException:
            await socket.close()
            raise
        self._spawn(self._beat(socket))
        return socket

    async def _kept(self, socket: ClientConnection) -> None:
        """Wait for the socket to drop, then dial again until one opens, unless told to stop."""
        attempt = 0
        while True:
            await socket.wait_closed()
            if self._socket is socket:
                self._socket, self._outbox = None, None
            if self._closed:
                return
            if socket.close_code == POLICY_VIOLATION:
                self._closed = True
                self._handlers.on_error(
                    NotConnected(f"the gateway refused the socket: {socket.close_reason}")
                )
                return
            while not self._closed:
                await asyncio.sleep(self._backoff.wait_s(attempt))
                attempt += 1
                try:
                    socket = await self._dial()
                except NotConnected as failed:
                    self._handlers.on_error(failed)
                    continue
                attempt = 0
                break
            if self._closed:
                return

    async def _read(self, socket: ClientConnection) -> None:
        with contextlib.suppress(ConnectionClosed):
            async for raw in socket:
                try:
                    entry = Entry.read_json(raw, "entry")
                except WireError as unreadable:
                    self._handlers.on_error(unreadable)
                    continue
                logger.debug(
                    "in  %s %s, %.0f ms after it was written",
                    entry.type,
                    entry.call,
                    (time.time() - entry.ts) * 1000,
                )
                try:
                    self._handlers.on_entry(entry)
                except Exception as failed:  # noqa: BLE001 - one entry's failure never stops the reader
                    self._handlers.on_error(failed)

    async def _write(self, socket: ClientConnection, outbox: "Outbox") -> None:
        with contextlib.suppress(ConnectionClosed):
            while True:
                await socket.send(await outbox.get())

    async def _beat(self, socket: ClientConnection) -> None:
        while self._socket is socket:
            await asyncio.sleep(self._ping_s)
            if self._socket is socket:
                self._handlers.on_beat()

    def _spawn(self, work: Awaitable[None]) -> None:
        task = asyncio.ensure_future(work)
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)


class Outbox:
    """The frames waiting for the socket, in the order `put` was called from any thread."""

    # One deque both sides append to: an append is atomic, so the order is the order of the calls.
    # Only the wake-up crosses to the loop; a frame handed over through `call_soon_threadsafe`
    # would be overtaken by one the loop puts directly before that callback runs.
    def __init__(self, loop: asyncio.AbstractEventLoop) -> None:
        """An empty outbox whose reader runs on `loop`."""
        self._frames: deque[str] = deque()
        self._loop = loop
        self._thread = threading.get_ident()
        self._wake = asyncio.Event()

    def put(self, text: str) -> None:
        """Queue one frame, from any thread."""
        self._frames.append(text)
        if threading.get_ident() == self._thread:
            self._wake.set()
        else:
            self._loop.call_soon_threadsafe(self._wake.set)

    async def get(self) -> str:
        """The oldest frame, once there is one."""
        while not self._frames:
            self._wake.clear()
            if not self._frames:
                await self._wake.wait()
        return self._frames.popleft()
