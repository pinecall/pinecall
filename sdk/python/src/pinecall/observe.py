"""Reading a log: one page of it, or the stream from a cursor on, folded by the reducer."""

import asyncio
import json
import random
from collections.abc import AsyncIterator
from dataclasses import dataclass

import httpx
from pydantic import BaseModel, ValidationError

from pinecall._endpoints import agent_log_url, call_log_url, signed
from pinecall.errors import PinecallError, Refused, WireError
from pinecall.wire._names import Env
from pinecall.wire.events import event_of
from pinecall.wire.frames import Entry, WireModel
from pinecall.wire.reduce import apply, initial_state, reduce
from pinecall.wire.state import State

RETRY_S = 1.0
RETRY_CAP_S = 30.0


@dataclass(frozen=True)
class Page:
    """One page of a log: the entries after the cursor, their folded state, and the next cursor."""

    entries: list[Entry]
    state: State
    live: bool
    """Whether the log is still open and more will follow."""
    next: int | None
    """The cursor for the next page; read it rather than the last entry's seq."""


class PageOnTheWire(BaseModel):
    """A page as the gateway writes it."""

    entries: list[Entry]
    live: bool = False
    next: int | None = None


@dataclass(frozen=True)
class Observation:
    """One entry, its event (None when this reader cannot read it), and the state folded so far."""

    entry: Entry
    event: WireModel | None
    state: State


@dataclass(frozen=True)
class Reader:
    """Where a log is read from, and how the request is signed."""

    base: str
    api_key: str
    env: Env | None

    def url_of(self, call: str | None, agent: str | None) -> str:
        """A call's log or an agent's own, named by exactly one of the two."""
        if (call is None) == (agent is None):
            raise PinecallError("a log is a call's or an agent's: name one of call= and agent=")
        return (
            call_log_url(self.base, call)
            if call is not None
            else agent_log_url(self.base, str(agent))
        )

    def headers(self, accept: str, after: int) -> dict[str, str]:
        """The key, the world, what to answer with, and the cursor a stream resumes from."""
        resumed = {"last-event-id": str(after)} if after > 0 else {}
        return signed(self.api_key, self.env) | {"accept": accept} | resumed


async def history(
    reader: Reader, *, call: str | None = None, agent: str | None = None, after: int = 0
) -> Page:
    """Read one page of a log after the cursor, and the state it folds to."""
    url = reader.url_of(call, agent)
    async with httpx.AsyncClient() as http:
        answered = await http.get(
            url, params=cursor(after), headers=reader.headers("application/json", after)
        )
    if answered.is_error:
        raise Refused(str(answered.status_code), answered.text)
    try:
        page = PageOnTheWire.model_validate_json(answered.content)
    except ValidationError as unreadable:
        raise WireError(
            f"the log page is not {{ entries, live, next }}: {unreadable}"
        ) from unreadable
    return Page(page.entries, reduce(page.entries), page.live, page.next)


async def observe(
    reader: Reader, *, call: str | None = None, agent: str | None = None, after: int = 0
) -> AsyncIterator[Observation]:
    """Stream a log from the cursor on, until the reader stops reading.

    A dropped stream is opened again from the last entry seen; a reader that fell behind gets
    `log.gap`, with a snapshot when there is one, then `log.caught_up`. Only a stream that never
    opened raises: that is a key or a call that is wrong, not a network that blinked.
    """
    url = reader.url_of(call, agent)
    state, attempt, opened = initial_state(), 0, False
    while True:
        try:
            async for entry in stream(url, reader, after):
                attempt, opened, after = 0, True, entry.seq
                state = apply(state, entry)
                yield Observation(entry, readable(entry), state)
        except (httpx.HTTPError, Refused):
            if not opened:
                raise
        attempt += 1
        await asyncio.sleep(random.random() * min(RETRY_CAP_S, RETRY_S * 2 ** (attempt - 1)))  # noqa: S311 - a delay


async def stream(url: str, reader: Reader, after: int) -> AsyncIterator[Entry]:
    """One server-sent-events connection, its entries until it closes."""
    headers = reader.headers("text/event-stream", after)
    async with (
        httpx.AsyncClient(timeout=httpx.Timeout(10.0, read=None)) as http,
        http.stream("GET", url, params=cursor(after), headers=headers) as answered,
    ):
        if answered.is_error:
            raise Refused(
                str(answered.status_code), (await answered.aread()).decode(errors="replace")
            )
        block: list[str] = []
        async for line in answered.aiter_lines():
            if line:
                block.append(line)
                continue
            entry = entry_in(block)
            block = []
            if entry is not None:
                yield entry


def entry_in(block: list[str]) -> Entry | None:
    """The entry one event carries, or None for a comment or a keep-alive."""
    data = "\n".join(
        line.removeprefix("data:").lstrip() for line in block if line.startswith("data:")
    )
    return None if not data else Entry.model_validate(json.loads(data))


def readable(entry: Entry) -> WireModel | None:
    """The entry's event, or None when it is a shape this version cannot read."""
    try:
        return event_of(entry)
    except WireError:
        return None


def cursor(after: int) -> dict[str, str]:
    """The query that asks for what came after the cursor."""
    return {"after": str(after)} if after > 0 else {}
