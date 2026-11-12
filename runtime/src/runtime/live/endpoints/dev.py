"""The console's dev verbs, relayed to the process that answers the console for an agent."""

from typing import Annotated

from fastapi import APIRouter, Query

from runtime.agents.auth import KnownAgent
from runtime.kit.text import JsonObject
from runtime.live.auth import CallsKey, EvalsKey, KnowledgeKey, MemoryKey, TalkKey, TheLive
from runtime.live.service import dev

router = APIRouter()

# The socket the console names, when it wants one app of the agent's and not the newest.
AppNamed = Annotated[str | None, Query(alias="app")]

# Five routes that differ in a word and a key, on purpose: each family asks for its own scope, and
# that is what the signature says.


@router.post("/v1/agents/{slug}/dev/chat/{verb}")
async def relay_chat(
    slug: KnownAgent, verb: str, said: JsonObject, actor: TalkKey, live: TheLive, app: AppNamed = None
) -> JsonObject:
    """A chat verb, answered by the process that answers the console for the agent."""
    return await dev.relay(live.sockets, live.holders, actor.scope, dev.Relay("chat", slug, verb, app), said)


@router.post("/v1/agents/{slug}/dev/knowledge/{verb}")
async def relay_knowledge(
    slug: KnownAgent, verb: str, said: JsonObject, actor: KnowledgeKey, live: TheLive, app: AppNamed = None
) -> JsonObject:
    """A knowledge verb, answered by the process that answers the console for the agent."""
    return await dev.relay(live.sockets, live.holders, actor.scope, dev.Relay("knowledge", slug, verb, app), said)


@router.post("/v1/agents/{slug}/dev/memory/{verb}")
async def relay_memory(
    slug: KnownAgent, verb: str, said: JsonObject, actor: MemoryKey, live: TheLive, app: AppNamed = None
) -> JsonObject:
    """A memory verb, answered by the process that answers the console for the agent."""
    return await dev.relay(live.sockets, live.holders, actor.scope, dev.Relay("memory", slug, verb, app), said)


@router.post("/v1/agents/{slug}/dev/view/{verb}")
async def relay_view(
    slug: KnownAgent, verb: str, said: JsonObject, actor: CallsKey, live: TheLive, app: AppNamed = None
) -> JsonObject:
    """The side panel beside a conversation, rendered by the app serving the call."""
    return await dev.relay(live.sockets, live.holders, actor.scope, dev.Relay("view", slug, verb, app), said)


@router.post("/v1/agents/{slug}/dev/evals/{verb}")
async def relay_evals(
    slug: KnownAgent, verb: str, said: JsonObject, actor: EvalsKey, live: TheLive, app: AppNamed = None
) -> JsonObject:
    """An evals verb, answered by the process that answers the console for the agent."""
    return await dev.relay(live.sockets, live.holders, actor.scope, dev.Relay("evals", slug, verb, app), said)
