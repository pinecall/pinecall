"""Server-sent events: a frame, the ping that keeps a stream alive, a stream's end, and a stream read."""

import asyncio
import json
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass

from fastapi.responses import StreamingResponse
from starlette.requests import Request

from runtime.kit.text import JsonObject, a_mapping

EVENT_STREAM = "text/event-stream"
PING_EVERY_S = 25.0
PING = ": ping\n\n"

# Proxies buffer a stream unless told not to; a browser reconnects after `retry`.
HEADERS = {"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}


def frame(data: str, *, event: str | None = None, id_: str | None = None) -> str:
    """One event as the wire carries it."""
    lines: list[str] = []
    if id_ is not None:
        lines.append(f"id: {id_}")
    if event is not None:
        lines.append(f"event: {event}")
    lines += [f"data: {line}" for line in data.split("\n")]
    return "\n".join(lines) + "\n\n"


def wants_sse(request: Request) -> bool:
    """Whether the client asked for a stream."""
    return EVENT_STREAM in request.headers.get("accept", "")


async def pace(
    frames: AsyncIterator[str], *, closing: asyncio.Event, ping_every_s: float = PING_EVERY_S
) -> AsyncIterator[str]:
    """The frames, a ping when quiet, and the end when the process is told to stop."""
    pending = asyncio.ensure_future(anext(frames, None))
    stopping = asyncio.ensure_future(closing.wait())
    try:
        while True:
            done, _ = await asyncio.wait({pending, stopping}, timeout=ping_every_s, return_when=asyncio.FIRST_COMPLETED)
            if stopping in done:
                return
            if pending not in done:
                yield PING
                continue
            got = pending.result()
            if got is None:
                return
            yield got
            pending = asyncio.ensure_future(anext(frames, None))
    finally:
        pending.cancel()
        stopping.cancel()


def stream(frames: AsyncIterator[str]) -> StreamingResponse:
    """The response a stream is answered with."""
    return StreamingResponse(frames, media_type=EVENT_STREAM, headers=HEADERS)


type Producer = Callable[[], Awaitable[AsyncIterator[str]]]


@dataclass(frozen=True, slots=True)
class Sent:
    """One event read off a stream: the id it came under, when it had one, and its JSON."""

    id: str | None
    data: JsonObject


# The reading half, for a process of ours that follows a stream of ours. `data:` holds the whole
# message (an entry with its seq and type, a command) and `id:` what it was sent under; `event:` and
# the pings are not read.
async def read_sse(lines: AsyncIterator[str]) -> AsyncIterator[Sent]:
    """Each JSON message of a server-sent event stream, with the id it came under."""
    data: list[str] = []
    sent_under: str | None = None
    async for raw in lines:
        line = raw.rstrip("\r\n")
        if line.startswith("data:"):
            data.append(line[5:].lstrip(" "))
        elif line.startswith("id:"):
            sent_under = line[3:].strip()
        elif not line and data:
            text: object = json.loads("\n".join(data))
            if a_mapping(text):
                yield Sent(sent_under, dict(text))
            data, sent_under = [], None
