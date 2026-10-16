"""Who may call the agents endpoints: which scopes open the settings, the pipeline, the apps, the line."""

from typing import Annotated

from fastapi import Depends, Request

from pinecall_runtime.agents.service.registry import AgentRegistry
from pinecall_runtime.enums import KeyScope
from pinecall_runtime.kit.auth import Actor, Authenticator, the_operator

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
