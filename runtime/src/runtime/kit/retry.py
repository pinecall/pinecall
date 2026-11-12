"""Asking again: the wait before a try, a call retried a few times or for as long as there is time, a poll."""

import asyncio
import logging
import random
import time
from collections.abc import Awaitable, Callable

from runtime.exceptions import UpstreamError

logger = logging.getLogger(__name__)

FIRST_WAIT_S = 0.5
LONGEST_WAIT_S = 8.0
# A quarter of the wait is taken off at random, so callers that failed together do not return together.
JITTER = 0.25
# A side that stays away is said once every so many tries, not at each.
SAID_EVERY = 10


def delay(attempt: int, *, first_s: float = FIRST_WAIT_S, longest_s: float = LONGEST_WAIT_S) -> float:
    """The wait before try number `attempt` (0 the first retry): doubled each time, capped, with jitter."""
    wait = min(first_s * 2.0**attempt, longest_s)
    return wait * (1 - JITTER * random.random())


# What may be asked again is the failure's own word (`UpstreamError.retryable`), said once where the
# vendor is called: a timeout, a lost connection, a 408, a 429, a 5xx. Anything else propagates at once.
async def retry[T](
    ask: Callable[[], Awaitable[T]],
    *,
    retries: int = 2,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
) -> T:
    """The answer of `ask`, tried again while it fails retryably; the wait it was told, when told one."""
    attempt = 0
    while True:
        try:
            return await ask()
        except UpstreamError as failed:
            if not failed.retryable or attempt >= retries:
                raise
            await sleep(failed.retry_after_s if failed.retry_after_s is not None else delay(attempt))
            attempt += 1


# For the other side of ours, which a restart takes away for seconds: asked again for as long as the
# caller can wait, and with no end where what is asked must not be lost (an entry of a call's log).
# A failure that is an answer (`retryable` false) propagates at once, as in `retry`.
async def keep_asking[T](
    ask: Callable[[], Awaitable[T]],
    *,
    within_s: float | None,
    what: str,
    longest_s: float = LONGEST_WAIT_S,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
) -> T:
    """The answer of `ask`, tried again while it fails retryably and there is time left; None is no limit."""
    started = time.monotonic()
    attempt = 0
    while True:
        try:
            return await ask()
        except UpstreamError as failed:
            wait = delay(attempt, longest_s=longest_s)
            is_late = within_s is not None and time.monotonic() - started + wait > within_s
            if not failed.retryable or is_late:
                raise
            attempt += 1
            if attempt % SAID_EVERY == 0:
                logger.warning("%s: still no answer after %d tries", what, attempt)
            await sleep(wait)


async def until[T](
    probe: Callable[[], Awaitable[T | None]],
    *,
    every_s: float,
    within_s: float,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
) -> T | None:
    """What `probe` answers once it answers something, asked every so often; None when the time runs out."""
    deadline = time.monotonic() + within_s
    while True:
        found = await probe()
        if found is not None:
            return found
        if time.monotonic() + every_s > deadline:
            return None
        await sleep(every_s)
