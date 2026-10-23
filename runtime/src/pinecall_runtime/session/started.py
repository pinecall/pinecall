"""The call.started entry: who called whom, on what, when, and what the call opened in."""

from pinecall_runtime.calls.context import CallContext
from pinecall_runtime.enums import Direction, Medium
from pinecall_runtime.kit.text import JsonObject
from pinecall_runtime.wire import events as wire


# The caller is always the far end: on an outbound call that is the `to`. The app cannot read a
# day a golden pinned off the clock, so the entry says it; the persona and what it expects are
# frozen here for the facts and its judge.
def started(context: CallContext, at: float, worker: str | None, *, medium: Medium) -> wire.CallStarted:
    """The entry a call opens with, parsed as the wire reads it."""
    endpoint = context.route.number or context.route.agent
    from_, to = (endpoint, context.caller) if context.direction is Direction.outbound else (context.caller, endpoint)
    started: JsonObject = {
        "channel": context.channel.value,
        "direction": context.direction.value,
        "from": from_,
        "to": to,
        "run": context.run,
        "persona": context.persona,
        "expects": list(context.expects) or None,
        "caller": None,
        "started_at": at,
        "env": context.env.value,
        "medium": medium.value,
    }
    if worker is not None:
        started["worker"] = worker
    if context.state:
        started["state"] = dict(context.state)
    if context.pinned_day:
        started["today"] = context.pinned_day.isoformat()
    return wire.CallStarted.parse(started, "call.started")
