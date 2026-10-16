"""Who is writing the state right now: a tool's name or a hook's, per task and never global."""

from collections.abc import Generator
from contextlib import contextmanager
from contextvars import ContextVar

# A ContextVar, not a module variable: one process serves many calls at once, and two tools
# running at the same time must not read each other's name. A task and `asyncio.to_thread`
# both start from a copy of the context they were started in.
_AUTHOR: ContextVar[str | None] = ContextVar("pinecall_author", default=None)


def current() -> str | None:
    """The author of a write made now, or None outside every tool and hook."""
    return _AUTHOR.get()


@contextmanager
def writing_as(author: str) -> Generator[None, None, None]:
    """Attribute every state write made inside the block to `author`."""
    token = _AUTHOR.set(author)
    try:
        yield
    finally:
        _AUTHOR.reset(token)
