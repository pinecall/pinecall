"""What a verb that waits answers: settled by the entry that says how it went, or by its ceiling."""

import asyncio
import concurrent.futures
from collections.abc import Awaitable, Callable, Generator
from dataclasses import dataclass
from typing import Generic, TypeVar

from pinecall.wire.parts import Supervisor, TransferMode

_T = TypeVar("_T")

# The runtime always answers with an entry; a ceiling only guards against a gateway that went away.
NO_ANSWER = "the runtime never said how it went"

THE_CALL_ENDED = "the call ended before it was answered"


@dataclass(frozen=True)
class Transferred:
    """How a transfer went: `ok=False` means the caller is still with the agent."""

    to: str
    mode: TransferMode | None
    ok: bool
    error: str | None = None


@dataclass(frozen=True)
class Attended:
    """How an ask for a person went: who took the line, or why nobody did."""

    ok: bool
    by: Supervisor | None
    error: str | None = None


class Answer(Generic[_T]):
    """An answer still coming: `await` it in an `async def`, or `.result()` it on a thread."""

    def __init__(self, future: concurrent.futures.Future[_T]) -> None:
        """Wrap the future the answer arrives on."""
        self._future = future

    def __await__(self) -> Generator[object, None, _T]:
        """Wait for it on the loop."""
        return asyncio.wrap_future(self._future).__await__()

    def result(self, within_s: float | None = None) -> _T:
        """Wait for it on a thread of your own; never from the loop, which is what answers it."""
        return self._future.result(within_s)

    def done(self) -> bool:
        """Whether it has come."""
        return self._future.done()


class Waiting(Generic[_T]):
    """The answers of one kind still coming for a call: settled together by the entry that comes."""

    def __init__(self, loop: asyncio.AbstractEventLoop | None) -> None:
        """Answers whose ceilings run on `loop`; with none, only an entry settles them."""
        self._loop = loop
        self._pending: list[concurrent.futures.Future[_T]] = []

    def answer(self, within_s: float, lapsed: _T) -> Answer[_T]:
        """A new answer, settled by the next entry, or with `lapsed` after `within_s`."""
        future: concurrent.futures.Future[_T] = concurrent.futures.Future()
        self._pending.append(future)
        if self._loop is not None:
            loop = self._loop
            ceiling = lambda: loop.call_later(within_s, settled, future, lapsed)  # noqa: E731 - scheduled from any thread
            loop.call_soon_threadsafe(ceiling)
        return Answer(future)

    def settle(self, answer: _T) -> None:
        """Settle every answer still waiting with this one."""
        pending, self._pending = self._pending, []
        for future in pending:
            settled(future, answer)


def settled(future: concurrent.futures.Future[_T], answer: _T) -> None:
    """Settle a future that nothing settled yet."""
    if not future.done():
        future.set_result(answer)


def scheduled(
    loop: asyncio.AbstractEventLoop | None, work: Callable[[], Awaitable[_T]]
) -> concurrent.futures.Future[_T]:
    """Run a coroutine on the loop from any thread, as a future either side can wait on."""
    if loop is None:
        raise RuntimeError("no loop serves this call")

    async def ran() -> _T:
        return await work()

    return asyncio.run_coroutine_threadsafe(ran(), loop)
