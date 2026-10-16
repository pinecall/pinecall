"""`view.render`, the one console verb an agent's own process answers: its class's panel."""

import asyncio

from pinecall.agent import Agent
from pinecall.errors import DevRefused
from pinecall.panels import Who, drawn
from pinecall.wire._names import JsonObject
from pinecall.wire.parts import DevVerb

# Word for word the TypeScript serve entry's.
ONLY_THE_VIEW = "this process answers only view.render: the console's other verbs are the CLI's"


async def answered(cls: type[Agent], slug: str, verb: DevVerb, asked: JsonObject) -> JsonObject:
    """The class's panel for the conversation asked, or a refusal with its status."""
    if verb != "view.render":
        raise DevRefused(404, ONLY_THE_VIEW)
    who = a_conversation(slug, asked)
    declared = getattr(cls, "_pinecall_panel")  # noqa: B009 - the class's own
    if declared is None:
        raise DevRefused(404, f"{slug} declares no view: nothing in this directory draws a panel")
    try:
        # On a thread: a panel reads the tenant's own systems, and may be an async def of its own.
        panel = await asyncio.to_thread(drawn, cls, declared, who)
    except Exception as failed:
        # The pane says it, and the conversation's screen keeps working.
        raise DevRefused(502, f"{slug}'s view failed: {failed}") from failed
    made: JsonObject = {"name": str(panel["name"]), "nodes": panel["nodes"]}  # pyright: ignore[reportAssignmentType]
    return made


def a_conversation(slug: str, asked: JsonObject) -> Who:
    """The conversation the console asked a panel for, refused when it names no contact or call."""
    named: dict[str, str] = {}
    for key in ("contact", "call"):
        value = asked.get(key)
        if not isinstance(value, str) or not value:
            raise DevRefused(422, f"{key} is a name, and it was missing")
        named[key] = value
    return Who(agent=slug, contact=named["contact"], call=named["call"])
