"""Knowledge's dependencies: the keys that open its endpoints, the box's embedder, and what paces a golden."""

from typing import Annotated

from fastapi import Depends
from starlette.requests import HTTPConnection

from runtime.actor import Actor
from runtime.agents.auth import KnownAgent, TheHolders
from runtime.auth import Authenticator
from runtime.enums import KeyScope
from runtime.exceptions import ServiceUnavailable
from runtime.handles import TheHttp, TheSessions, TheVault
from runtime.knowledge.service.embedder import Embedder, embedder_of
from runtime.platform import service as platform

KnowledgeKey = Annotated[Actor, Depends(Authenticator(KeyScope.knowledge))]
MemoryKey = Annotated[Actor, Depends(Authenticator(KeyScope.memory))]


# Read in a transaction of its own, closed before the endpoint runs: an edited row takes from the
# next request, and no connection of the request's is held while the vendor embeds.
async def the_embedder(sessions: TheSessions, vault: TheVault, http: TheHttp) -> Embedder:
    """The embedder the providers row names, on the box's key; refused on a box whose row names none."""
    async with sessions.begin() as session:
        embedder = await embedder_of(session, vault, http)
    if embedder is None:
        raise ServiceUnavailable(
            "this box has no embedder: the providers row names none under `embedding`, so nothing can be "
            "pushed, searched or remembered"
        )
    return embedder


TheEmbedder = Annotated[Embedder, Depends(the_embedder)]


def extraction_runs_of(connection: HTTPConnection) -> platform.AttemptThrottle:
    """The goldens of extraction an org may run a minute."""
    throttle: platform.AttemptThrottle = connection.state.extraction_runs
    return throttle


TheExtractionRuns = Annotated[platform.AttemptThrottle, Depends(extraction_runs_of)]


# Counted by org, not by key: a run is up to fifty model calls on keys the box may lend.
async def pace_extraction_run(actor: MemoryKey, runs: TheExtractionRuns) -> None:
    """Count one more golden of extraction for the key's org; refused past the minute's ceiling."""
    await runs.check(f"{actor.org} memory/extraction", "extraction runs from this org")


an_extraction_run_a_time = Depends(pace_extraction_run)


# No session is asked for here, on purpose: the golden this opens asks a model fifty times, and a
# transaction begun by a dependency would sit idle under all of them (`agents.auth.the_held_agent`
# reads the agent's row on the request's session). The golden reads the agent itself, and lets go.
def the_held_slug(slug: KnownAgent, actor: MemoryKey, holders: TheHolders) -> str:
    """The path's agent, the org's own and held by an app in the key's scope now; refused when none holds it."""
    holders.get_holder(actor.scope, slug)
    return slug


TheHeldSlug = Annotated[str, Depends(the_held_slug)]
