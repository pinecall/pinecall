"""Loops that go on: a pass that raises is said and survived, and each loop a process runs is known by name."""

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable, Generator
from contextlib import contextmanager
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

# After a pass that failed, the wait before the next grows to this and no further.
LONGEST_PAUSE_S = 60.0


@dataclass
class Survival:
    """How the block ended: `failed` once it raised and was said instead."""

    failed: bool = False


# A task cancelled while it waits on a database gets its CancelledError back wrapped in the driver's
# error: a loop that caught the error and went on would never end, and its process never stop.
def is_cancellation(error: BaseException) -> bool:
    """Whether an error is the task's own cancellation, wrapped or not, which a loop lets through."""
    seen: BaseException | None = error
    for _ in range(8):
        if seen is None:
            return False
        if isinstance(seen, asyncio.CancelledError):
            return True
        seen = getattr(seen, "orig", None) or seen.__cause__ or seen.__context__
    return False


# Around the body of an item or of a pass, in sync or async code: what it raises is said and the
# loop goes on to the next, so one item it cannot read never stops what it does for every other. A
# cancellation goes through: it is the loop being stopped. `on` names what it was on. What the loop
# itself ends on (a socket that closed) is named in `unless`, and raised.
@contextmanager
def survive(what: str, on: str | None = None, *, unless: tuple[type[Exception], ...] = ()) -> Generator[Survival]:
    """Say what raised in the block, and where, instead of raising it; cancellation still raises."""
    outcome = Survival()
    try:
        yield outcome
    except Exception as failed:
        if is_cancellation(failed) or isinstance(failed, unless):
            raise
        outcome.failed = True
        logger.warning("%s failed%s", what, "" if on is None else f" on {on}", exc_info=True)


@dataclass(frozen=True, slots=True)
class Bound:
    """A loop with what its pass needs already given: ready to be started."""

    name: str
    every_s: float
    each: Callable[[], Awaitable[None]]


@dataclass(frozen=True, slots=True)
class Loop[**P]:
    """One loop a domain owns: its name, how often it passes, and the pass."""

    name: str
    every_s: float
    each: Callable[P, Awaitable[None]]

    def bind(self, *args: P.args, **kwargs: P.kwargs) -> Bound:
        """The loop with its pass's arguments given, as the entrypoint that starts it knows them."""
        return Bound(self.name, self.every_s, lambda: self.each(*args, **kwargs))


def loop[**P](name: str, *, every_s: float) -> Callable[[Callable[P, Awaitable[None]]], Loop[P]]:
    """Declare a function as one pass of a loop; the entrypoint binds what it needs and starts it."""

    def declare(each: Callable[P, Awaitable[None]]) -> Loop[P]:
        return Loop(name, every_s, each)

    return declare


@dataclass(frozen=True, slots=True)
class Beat:
    """How one loop stands: alive or not, when its last pass ended, how many passes failed."""

    name: str
    alive: bool
    last_pass_s: float | None
    failures: int


@dataclass
class Loops:
    """The loops one process runs: started by name, every pass survived, each one's heartbeat kept."""

    _tasks: dict[str, asyncio.Task[None]] = field(default_factory=dict[str, asyncio.Task[None]])
    _passed_at: dict[str, float] = field(default_factory=dict[str, float])
    _failures: dict[str, int] = field(default_factory=dict[str, int])

    def start(self, bound: Bound) -> None:
        """Start the loop; a name runs once."""
        if bound.name in self._tasks:
            raise ValueError(f"a loop named {bound.name} runs already")
        self._failures[bound.name] = 0
        self._tasks[bound.name] = asyncio.create_task(self._run(bound), name=f"loop:{bound.name}")

    async def stop(self) -> None:
        """Cancel every loop and wait for each to end."""
        for task in self._tasks.values():
            task.cancel()
        await asyncio.gather(*self._tasks.values(), return_exceptions=True)
        self._tasks.clear()

    def beats(self) -> list[Beat]:
        """Every loop's heartbeat, by name: what `/metrics` reports."""
        moment = time.monotonic()
        return [
            Beat(
                name,
                alive=not task.done(),
                last_pass_s=None if name not in self._passed_at else moment - self._passed_at[name],
                failures=self._failures[name],
            )
            for name, task in sorted(self._tasks.items())
        ]

    # A pass that failed is said by `survive`; the next waits twice as long, up to a minute, so a
    # database that is down is not asked every second.
    async def _run(self, bound: Bound) -> None:
        pause = bound.every_s
        while True:
            with survive(f"a pass of {bound.name}") as outcome:
                await bound.each()
            self._passed_at[bound.name] = time.monotonic()
            if outcome.failed:
                self._failures[bound.name] += 1
                pause = min(max(pause, 1.0) * 2, LONGEST_PAUSE_S)
            else:
                pause = bound.every_s
            await asyncio.sleep(pause)
