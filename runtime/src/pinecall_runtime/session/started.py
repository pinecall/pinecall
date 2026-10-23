"""The call.started entry: who called whom, on what, when, and what the call opened in."""

from dataclasses import asdict

from pinecall_runtime.calls.context import CallContext, Contact
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
        "caller": _caller_of(context.contact),
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
    if context.metadata:
        started["metadata"] = dict(context.metadata)
    return wire.CallStarted.parse(started, "call.started")


# The contact the call was opened with is who is on the line: the hook reads it as `call.contact`, the
# facts file the call under it and an erasure by it finds the call. Nothing named, nobody yet.
def _caller_of(contact: Contact | None) -> JsonObject | None:
    named = {} if contact is None else {field: value for field, value in asdict(contact).items() if value is not None}
    return named or None
