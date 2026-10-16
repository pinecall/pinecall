"""What the worker's client rides on: a call's entries down one socket, SSE in, retries, headers."""

import asyncio
import json
import logging
import time
from collections.abc import AsyncIterator, Awaitable, Callable, Iterator, Mapping, Sequence

import httpx
from opentelemetry import propagate
from websockets.asyncio.client import ClientConnection, connect
from websockets.exceptions import ConnectionClosed, InvalidHandshake

from pinecall_runtime.calls import service as calls
from pinecall_runtime.exceptions import GatewayUnavailable
from pinecall_runtime.kit.text import JsonObject
from pinecall_runtime.wire.base import BatchedEntry, Entry

logger = logging.getLogger(__name__)

# A caller is waiting on the line.
TIMEOUT_S = 5.0

# A restarting gateway is back in seconds; the cap keeps the log catching up after it.
FIRST_WAIT_S = 0.5
LONGEST_WAIT_S = 5.0
SAID_EVERY = 10

NOT_SERVED = 404

# The header a balancer keeps a call's requests on one gateway by: `/v1/calls/{call}/...`.
CALL_HEADER = "Pinecall-Call"
CALL_AT = 3

# A stream is timed only on connect: a quiet one is kept open by the gateway's ping every 25 s.
STREAMED = httpx.Timeout(TIMEOUT_S, read=None)

EVENT_STREAM = "text/event-stream"


# One batch is out at a time (the call's writer sends the next when this one is answered), so an
# answer is the last frame sent. An answer that does not come within the request's timeout is
# not waited for past it: the socket is dropped, and the retry asks again on a new one.
class EntriesStream:
    """A call's batches down one WebSocket to the gateway, each answered with its seqs."""

    def __init__(self, url: str, headers: Mapping[str, str], call: str) -> None:
        """Not connected yet: the first batch connects."""
        self.url = url
        self.headers = dict(headers)
        self.call = call
        self.socket: ClientConnection | None = None
        # True once the gateway refused the upgrade: it has no such endpoint.
        self.unserved = False
        self._sending = asyncio.Lock()

    async def append_many(self, entries: Sequence[BatchedEntry], *, after: int) -> list[Entry]:
        """Send the batch and read its answer; GatewayUnavailable when the socket or the log did."""
        frame = calls.AppendEntriesRequest(after=after, entries=list(entries)).model_dump_json()
        async with self._sending:
            socket = await self._connected()
            try:
                await socket.send(frame)
                raw = await asyncio.wait_for(socket.recv(), TIMEOUT_S)
            except (ConnectionClosed, OSError, TimeoutError) as lost:
                await self.close()
                raise GatewayUnavailable(f"WS {self.url}: {lost}") from lost
        answer = json.loads(raw)
        if isinstance(answer, dict) and "refused" in answer:
            refused = calls.AppendEntriesRefused.model_validate(answer)
            raise GatewayUnavailable(f"WS {self.url}: {refused.status} {refused.refused}", answered=refused.status)
        return calls.AppendEntriesResponse.model_validate(answer).entries

    async def close(self) -> None:
        """Close the socket; the next batch opens another."""
        socket, self.socket = self.socket, None
        if socket is not None:
            await socket.close()

    async def _connected(self) -> ClientConnection:
        if self.socket is not None:
            return self.socket
        try:
            self.socket = await connect(self.url, additional_headers=self.headers, open_timeout=TIMEOUT_S)
        except InvalidHandshake as refused:
            self.unserved = True
            raise GatewayUnavailable(f"WS {self.url}: {refused}", answered=NOT_SERVED) from refused
        except (OSError, TimeoutError) as unreachable:
            raise GatewayUnavailable(f"WS {self.url}: {unreachable}") from unreachable
        return self.socket


# `data:` holds the whole entry, its seq and type included: `id:`, `event:` and comments are
# not read.
async def server_sent(lines: AsyncIterator[str]) -> AsyncIterator[JsonObject]:
    """Each JSON message of a server-sent event stream."""
    data: list[str] = []
    async for raw in lines:
        line = raw.rstrip("\r\n")
        if line.startswith("data:"):
            data.append(line[5:].lstrip(" "))
        elif not line and data:
            text = json.loads("\n".join(data))
            data = []
            if isinstance(text, dict):
                yield text


def waits() -> Iterator[float]:
    """The waits between tries: doubling from half a second to five."""
    wait = FIRST_WAIT_S
    while True:
        yield wait
        wait = min(wait * 2, LONGEST_WAIT_S)


def away(refused: GatewayUnavailable) -> bool:
    """Whether the gateway is away (unreachable or a 5xx), which a retry outlasts."""
    return refused.answered is None or refused.answered >= httpx.codes.INTERNAL_SERVER_ERROR


# A 4xx is an answer. `within_s` bounds a request that has a deadline (a tool); None retries for
# as long as the call lasts (an entry).
async def again[T](attempt: Callable[[], Awaitable[T]], within_s: float | None, what: str) -> T:
    """Run the attempt, retrying while the gateway is away and there is time left."""
    started = time.monotonic()
    pauses = waits()
    tries = 0
    while True:
        tries += 1
        try:
            return await attempt()
        except GatewayUnavailable as refused:
            pause = next(pauses)
            late = within_s is not None and time.monotonic() - started + pause > within_s
            if not away(refused) or late:
                raise
            if tries % SAID_EVERY == 0:
                logger.warning("%s: the gateway is still away after %d tries", what, tries)
            await asyncio.sleep(pause)


# The worker's current span rides each request as W3C traceparent, so the gateway's handling of an
# append joins the turn's trace; with no tracer set (no PINECALL_OTLP_ENDPOINT) nothing is added.
def traced() -> dict[str, str]:
    """The headers that carry the current trace to the gateway; none when nothing traces."""
    carried: dict[str, str] = {}
    propagate.inject(carried)
    return carried


# A box of several gateways hashes this header at its balancer, so a call's requests land on one
# gateway while it lives: its first sights, its sequencer's fills and its writers stay rare. Only
# a speed-up: any gateway serves any endpoint, and an old worker sends none.
def affine(path: str) -> dict[str, str]:
    """The header naming the call a request is about, when its path names one."""
    parts = path.split("/")
    if len(parts) > CALL_AT and parts[1:CALL_AT] == ["v1", "calls"] and parts[CALL_AT]:
        return {CALL_HEADER: parts[CALL_AT]}
    return {}
