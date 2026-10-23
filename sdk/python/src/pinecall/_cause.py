"""The cause a `state.set` names for a write: the tool, the event or the hook that made it."""

from typing import Literal

from pinecall import _author
from pinecall.call import CallWorld
from pinecall.wire.parts import StateCause, StateCauseEvent, StateCauseHook, StateCauseTool

# The hooks whose writes the wire names; `on_end` writes after the call is over, and none is sent.
HOOKS: dict[str, Literal["on_call", "on_memory"]] = {"on_call": "on_call", "on_memory": "on_memory"}


def cause_of(author: str, world: CallWorld) -> StateCause | None:
    """What to say of a write by its author, read where it is made.

    The tool call id is on the context and the event being handled is on the call; a writer the
    wire has no kind for says nothing.
    """
    if author.startswith(_author.HOOK):
        hook = HOOKS.get(author.removeprefix(_author.HOOK))
        return None if hook is None else StateCauseHook(kind="hook", hook=hook)
    if author.startswith(_author.EVENT):
        if world.cause is None:
            return None
        name, seq = world.cause
        return StateCauseEvent(kind="event", name=name, seq=seq)
    call_id = _author.current_tool_call()
    return None if call_id is None else StateCauseTool(kind="tool", tool=author, call_id=call_id)
