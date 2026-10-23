"""Who is writing the state right now: a tool's name or a hook's, per task and never global."""

from collections.abc import Generator
from contextlib import contextmanager
from contextvars import ContextVar

# A ContextVar, not a module variable: one process serves many calls at once, and two tools
# running at the same time must not read each other's name. A task and `asyncio.to_thread`
# both start from a copy of the context they were started in.
_AUTHOR: ContextVar[str | None] = ContextVar("pinecall_author", default=None)


# The model's id for the tool call a write is made in, so its cause names the call too.
_TOOL_CALL: ContextVar[str | None] = ContextVar("pinecall_tool_call", default=None)

HOOK = "hook:"
EVENT = "event:"


def hook(name: str) -> str:
    """What the author of a write inside the lifecycle hook `name` reads."""
    return f"{HOOK}{name}"


def event(name: str) -> str:
    """What the author of a write inside the handler of the outside event `name` reads."""
    return f"{EVENT}{name}"


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


def current_tool_call() -> str | None:
    """The model's id for the tool call running now, or None outside one."""
    return _TOOL_CALL.get()


@contextmanager
def calling(call_id: str) -> Generator[None, None, None]:
    """Run the block as the tool call `call_id`: the writes inside it say which call made them."""
    token = _TOOL_CALL.set(call_id)
    try:
        yield
    finally:
        _TOOL_CALL.reset(token)
