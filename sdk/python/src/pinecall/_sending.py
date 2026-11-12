"""What the bridge sends for a call: the blocks and tools that changed, the state and its screen."""

import json
from collections.abc import Awaitable, Callable

from pydantic import TypeAdapter

from pinecall._calls import Call
from pinecall._failures import unrendered
from pinecall._live import Live
from pinecall._screened import redrawn, scene_tool_of, state_with
from pinecall.blocks import render
from pinecall.call import CallLine
from pinecall.client import Client, Found
from pinecall.screen import SCREEN
from pinecall.wire._names import JsonObject
from pinecall.wire.events_turn import MemoryOps
from pinecall.wire.parts import ToolSpec

# Whatever a tool returns or a field holds, made JSON: dataclasses, models, dates, tuples.
ANYTHING: TypeAdapter[object] = TypeAdapter(object)


def synced(served: Live) -> None:
    """Send each block whose text changed, the tools if they moved, the screen if it did.

    A view that cannot be rendered fails its call and no other: the model keeps the one it had.
    """
    try:
        show(served)
    except Exception as failed:  # noqa: BLE001 - a class's own failure is the call's, never the loop's
        unrendered(served.call, failed)


def show(served: Live) -> None:
    """Send what changed of the prompt, the tools and the screen."""
    with served.lock:
        rendered = render(
            served.agent,
            served.world.line(),
            resumed=served.resumed,
            remembered=served.remembered,
            rules=served.rules,
        )
        for block in rendered.blocks:
            # A block never sent is empty, as the runtime starts it: an empty one costs nothing.
            if block.text == served.sent.get(block.name, ""):
                continue
            served.sent[block.name] = block.text
            served.call.set_prompt(block.name, block.text)
        visible = visible_tools(served)
        shown = json.dumps([spec.written() for spec in visible])
        if shown != served.tools_shown:
            served.tools_shown = shown
            served.call.set_tools(visible)
        if served.draws and redrawn(served.agent.screen(), served.world.shown, served.screened):
            served.call.set_state(state_of(served), [SCREEN])


def visible_tools(served: Live) -> list[ToolSpec]:
    """While a tool waits for an answer only the tool that gives it; else every tool shown now."""
    asked = served.asking.open
    if asked is not None:
        return [asked]
    return [*served.agent.visible_tools(), *served.transfers, *scene_tool_of(served.cls)]


def state_of(served: Live) -> JsonObject:
    """The call's state as the gateway is told it: the agent's own, and its screen once drawn."""
    return jsonable(state_with(served.agent.snapshot(), served.screened))


def recalled(ops: MemoryOps) -> list[str]:
    """What a recall brought, as `remembers` reads it: each fact's text and its category."""
    return [
        word
        for op in ops.ops
        if op.op == "recall"
        for fact in op.facts
        for word in (fact.text, fact.category or "")
    ]


def jsonable(value: object) -> JsonObject:
    """A snapshot as the wire carries it: dataclasses, models and dates made JSON."""
    made: JsonObject = ANYTHING.dump_python(value, mode="json")
    return made


def as_object(data: object) -> JsonObject:
    """A log line's data is an object on the wire: anything else is put under `value`."""
    if data is None:
        return {}
    made = ANYTHING.dump_python(data, mode="json")
    return made if isinstance(made, dict) else {"value": made}  # pyright: ignore[reportUnknownVariableType]


def searching(client: Client, call: Call) -> Callable[[str, int | None], Awaitable[list[Found]]]:
    """The gateway's search, for this call."""
    return lambda query, k: client.search(call.id, query, k)


def line_of(call: Call) -> CallLine:
    """The call as its first entry said it, for the instance that serves it."""
    contact = call.contact.id if call.contact is not None and call.contact.id else call.from_
    return CallLine(
        id=call.id,
        contact=contact or "",
        from_=call.from_,
        to=call.to,
        channel=call.channel or "phone",
        direction=call.direction,
        caller=call.contact,
        metadata=call.metadata,
        medium=call.medium,
        today=call.today,
        claimed=call.claimed,
    )
