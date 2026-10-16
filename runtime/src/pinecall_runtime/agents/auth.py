"""Who may call the agents endpoints: which scopes open the settings, the pipeline, the apps, the line."""

from typing import Annotated

from fastapi import Depends, Query, Request

from pinecall_runtime.agents.service.registry import AgentRegistry
from pinecall_runtime.enums import KeyScope
from pinecall_runtime.exceptions import NotFound
from pinecall_runtime.kit.auth import Actor, Authenticator, actor_of, the_operator

NO_SUCH_AGENT = "no agent {slug} in this org: `pinecall agent list` names the ones there are"

# A supervisor's key opens the words of an agent; the pipeline's key opens everything of it.
WordsKey = Annotated[Actor, Depends(Authenticator(KeyScope.pipeline, KeyScope.words))]
PipelineKey = Annotated[Actor, Depends(Authenticator(KeyScope.pipeline))]
CallsKey = Annotated[Actor, Depends(Authenticator(KeyScope.calls))]
UsageKey = Annotated[Actor, Depends(Authenticator(KeyScope.usage))]
TalkKey = Annotated[Actor, Depends(Authenticator(KeyScope.talk))]
AppKey = Annotated[Actor, Depends(Authenticator(KeyScope.app))]
# A worker asks with its fleet's key; a tenant's own worker with an app key.
WorkerKey = Annotated[Actor, Depends(Authenticator(KeyScope.app, KeyScope.fleet))]
DeclarationKey = Annotated[Actor, Depends(Authenticator(KeyScope.app, KeyScope.calls, KeyScope.fleet))]
FleetKey = Annotated[Actor, Depends(Authenticator(KeyScope.fleet))]
TheOperator = Annotated[Actor, Depends(the_operator)]


def sees_every_scope(actor: Actor) -> bool:
    """Whether the key reads every holder's agents in its org and env: a team key that holds agents."""
    return {KeyScope.team, KeyScope.app} <= actor.scopes


def registry_of(request: Request) -> AgentRegistry:
    """The agents the app sockets hold, as the lifespan built them."""
    registry: AgentRegistry = request.app.state.registry
    return registry


TheRegistry = Annotated[AgentRegistry, Depends(registry_of)]


# A slug typed wrong answered a plausible empty page before; another org's slug is the same 404.
async def known_agent(slug: str, request: Request) -> str:
    """The path's agent, one the key's org has: held now, or held once. Any other slug is 404."""
    actor = actor_of(request)
    if actor is None or await registry_of(request).is_known(actor.org, slug):
        return slug
    raise NotFound(NO_SUCH_AGENT.format(slug=slug))


KnownAgent = Annotated[str, Depends(known_agent)]


async def known_filter(request: Request, agent: Annotated[str | None, Query()] = None) -> str | None:
    """A list's `?agent=`: none is every agent; one the org never held is 404, never an empty page."""
    return None if agent is None else await known_agent(agent, request)


KnownFilter = Annotated[str | None, Depends(known_filter)]
