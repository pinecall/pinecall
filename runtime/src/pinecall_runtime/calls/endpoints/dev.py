"""The console's dev verbs, relayed to the process that answers the console for an agent."""

from typing import Annotated

from fastapi import APIRouter, Query

from pinecall_runtime.agents.auth import KnownAgent
from pinecall_runtime.calls.auth import (
    CallsKey,
    EvalsKey,
    KnowledgeKey,
    MemoryKey,
    TalkKey,
    TheServing,
)
from pinecall_runtime.calls.service import dev
from pinecall_runtime.kit.text import JsonObject

router = APIRouter()

# The socket the console names, when it wants one app of the agent's and not the newest.
AppNamed = Annotated[str | None, Query(alias="app")]


@router.post("/v1/agents/{slug}/dev/chat/{verb}")
async def relay_chat(
    slug: KnownAgent, verb: str, said: JsonObject, actor: TalkKey, serving: TheServing, app: AppNamed = None
) -> JsonObject:
    """A chat verb, answered by the process that answers the console for the agent."""
    return await dev.relay(serving, actor.scope, dev.Relay("chat", slug, verb), said, app)


@router.post("/v1/agents/{slug}/dev/knowledge/{verb}")
async def relay_knowledge(
    slug: KnownAgent, verb: str, said: JsonObject, actor: KnowledgeKey, serving: TheServing, app: AppNamed = None
) -> JsonObject:
    """A knowledge verb, answered by the process that answers the console for the agent."""
    return await dev.relay(serving, actor.scope, dev.Relay("knowledge", slug, verb), said, app)


@router.post("/v1/agents/{slug}/dev/memory/{verb}")
async def relay_memory(
    slug: KnownAgent, verb: str, said: JsonObject, actor: MemoryKey, serving: TheServing, app: AppNamed = None
) -> JsonObject:
    """A memory verb, answered by the process that answers the console for the agent."""
    return await dev.relay(serving, actor.scope, dev.Relay("memory", slug, verb), said, app)


@router.post("/v1/agents/{slug}/dev/view/{verb}")
async def relay_view(
    slug: KnownAgent, verb: str, said: JsonObject, actor: CallsKey, serving: TheServing, app: AppNamed = None
) -> JsonObject:
    """The side panel beside a conversation, rendered by the app serving the call."""
    return await dev.relay(serving, actor.scope, dev.Relay("view", slug, verb), said, app)


@router.post("/v1/agents/{slug}/dev/evals/{verb}")
async def relay_evals(
    slug: KnownAgent, verb: str, said: JsonObject, actor: EvalsKey, serving: TheServing, app: AppNamed = None
) -> JsonObject:
    """An evals verb, answered by the process that answers the console for the agent."""
    return await dev.relay(serving, actor.scope, dev.Relay("evals", slug, verb), said, app)
