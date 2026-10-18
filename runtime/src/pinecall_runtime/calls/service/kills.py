"""An agent killed: every app socket that holds it in an env lets go of it, on whichever gateway."""

from pinecall_runtime.agents.service import registry as agents_registry
from pinecall_runtime.calls.service.live import Live
from pinecall_runtime.enums import Env


# Each socket keeps its other agents; the one killed is told why, and declares it no more.
async def kill_agent(
    live: Live, registry: agents_registry.AgentRegistry, org: str, env: Env, slug: str, why: str
) -> list[agents_registry.SocketId]:
    """Every socket holding the agent in the org's env, in any scope, told to let go of it; their ids."""
    holding = sockets_holding(registry, org, env, slug)
    killed: list[agents_registry.SocketId] = []
    for app in live.apps_of(org, env):
        if app.app in holding:
            await app.kill(slug, why)
            killed.append(app.app)
    return killed


def sockets_holding(
    registry: agents_registry.AgentRegistry, org: str, env: Env, slug: str
) -> frozenset[agents_registry.SocketId]:
    """Every socket that holds the agent in the org's env, in any scope, on any gateway."""
    return frozenset(
        item.owner
        for (owner, name), kept in registry.holders.items()
        if owner.org == org and owner.env == env and name == slug
        for item in kept
    )
