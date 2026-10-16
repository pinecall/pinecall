"""Running a tenant's method under its author: a `def` or an `async def`, from a loop or not."""

import asyncio
import inspect
from collections.abc import Awaitable, Callable

from pinecall._author import writing_as


def called(author: str, method: Callable[..., object], *args: object, **kwargs: object) -> object:
    """Run the method to its end with no loop running: an `async def` gets a loop of its own."""
    with writing_as(author):
        return finished(method(*args, **kwargs))


def finished(result: object) -> object:
    """What a method answered, run to its end on a loop of its own when it is a coroutine."""
    if inspect.isawaitable(result):
        return asyncio.run(_awaited(result))
    return result


async def run(
    author: str, method: Callable[..., object], *args: object, **kwargs: object
) -> object:
    """Run the method from a loop: an `async def` on it, a `def` on a thread."""
    with writing_as(author):
        if inspect.iscoroutinefunction(method):
            return await method(*args, **kwargs)
        # The thread starts from a copy of this context, so it writes as the same author.
        result = await asyncio.to_thread(method, *args, **kwargs)
        if inspect.isawaitable(result):
            return await result
        return result


async def _awaited(result: Awaitable[object]) -> object:
    return await result
