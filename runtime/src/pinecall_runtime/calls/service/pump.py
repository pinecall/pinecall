"""A bound call's pump: what any gateway writes to it, sent down its app socket in seq order."""

import logging
from collections.abc import Awaitable, Callable, Sequence

from pinecall_runtime.calls.logs import Log
from pinecall_runtime.kit.loops import survived
from pinecall_runtime.wire.base import Entry

type Send = Callable[[Entry], Awaitable[None]]

logger = logging.getLogger(__name__)

# What a stream says of itself, never sent to an app.
MARKERS = frozenset({"log.caught_up", "log.gap"})
# What a socket that is gone raises: the pump ends there, it does not skip the entry.
GONE = (OSError, RuntimeError)


# The app runs the call's tools and holds its state: it is sent them as they were written, from
# `after`; `then` goes down right after the first entry (the tools still waiting, after
# call.attached). The stream follows the log through the relay, so an entry another gateway
# wrote reaches the socket here, and it ends when the call does.
async def pump(log: Log, after: int, send: Send, then: Sequence[Entry]) -> None:
    """Send the call's entries to its socket until the call ends or the socket stops taking them."""
    waiting = list(then)
    try:
        async for entry in log.stream(after=after):
            if entry.type in MARKERS:
                continue
            # An entry that cannot be sent is said with its call and seq and the next goes: a pump that
            # ended on it would leave the app deaf to the call, its tool calls unanswered to their deadline.
            with survived("sending an entry down its call's socket", f"{log.call} seq {entry.seq}", unless=GONE):
                await send(await log.opened(entry))
                for tool_call in waiting:
                    await send(await log.opened(tool_call))
                waiting = []
    except GONE:
        logger.warning("an app socket stopped taking its call's entries", exc_info=True)
