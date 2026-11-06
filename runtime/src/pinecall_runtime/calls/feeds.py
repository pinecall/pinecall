"""What the feeds say of a call: its lifecycle with no content, a tool's name and seconds, and news no log holds."""

import time

from pinecall_runtime.calls.relay import BOX_CHANNEL, FEED_CHANNEL
from pinecall_runtime.calls.repository.heads import Claimant
from pinecall_runtime.enums import Env
from pinecall_runtime.exceptions import ValidationError
from pinecall_runtime.kit.auth import Scope
from pinecall_runtime.wire.base import Entry, WireModel
from pinecall_runtime.wire.feed import ToolFailed, ToolRan
from pinecall_runtime.wire.parts import ToolResult

# A call sealed and a call judged: a list redraws its row then, so they are on the feed, with no
# data, since the outcome and the verdicts are the call's content; a reader reads them off the call.
ONLY_THAT_IT_HAPPENED = frozenset({"call.summary", "call.score"})

# What an org's feed and the box's carry: the lifecycle, never the content of a call.
ORG_EVENTS = frozenset(
    {
        "agent.registered",
        "agent.detached",
        "call.ringing",
        "call.dialing",
        "call.started",
        "call.ended",
        "attention.requested",
        "attention.answered",
        "supervisor.took_over",
        "supervisor.released",
        "call.summary",
        "call.score",
    }
)


def on_the_feeds(entry: Entry) -> Entry | None:
    """The entry as the feeds carry it, or None for one they do not: the lifecycle alone, its content left out."""
    if entry.type not in ORG_EVENTS:
        return None
    return entry.model_copy(update={"data": {}}) if entry.type in ONLY_THAT_IT_HAPPENED else entry


# An agent's own entries serve both envs, so they reach the org's feed in each.
def feed_channels(claimant: Claimant) -> tuple[str, ...]:
    """The box's channel and the claimant's org's, in each env the entry serves."""
    envs = tuple(Env) if claimant.env is None else (claimant.env,)
    return (BOX_CHANNEL, *(FEED_CHANNEL.format(org=claimant.org, env=env.value) for env in envs))


# Said with the tool's name and seconds, never its error, arguments or output, which are the call's content.
def tool_news(entry: Entry, claimant: Claimant) -> tuple[Scope, str, WireModel] | None:
    """What the org's feed says of a tool.result: where, the kind (`tool.ran`, `tool.failed`) and the event."""
    try:
        result = ToolResult.parse(entry.data, entry.type)
    except ValidationError:
        return None
    if claimant.env is None or entry.call is None:
        return None
    scope = Scope(claimant.org, claimant.env)
    if result.error is None:
        return (
            scope,
            "tool.ran",
            ToolRan(call=entry.call, agent=entry.agent, name=result.name, duration_s=result.duration_s),
        )
    return (
        scope,
        "tool.failed",
        ToolFailed(call=entry.call, agent=entry.agent, name=result.name, duration_s=result.duration_s),
    )


# What a feed says of a change no log holds: its type and ids, the moment it is said, kept nowhere.
def news(kind: str, event: WireModel) -> Entry:
    """An entry of the feed for something that changed, said once and never stored."""
    return Entry(seq=0, ts=time.time(), call=None, agent="", type=kind, ephemeral=True, data=event.dump())
