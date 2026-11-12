"""The agents' dependencies: the keys that open its endpoints, the agent of a path loaded, and what a request reads."""

from typing import Annotated, Any, Protocol

from fastapi import Depends, Query, Request
from starlette.requests import HTTPConnection

from runtime.accounts.auth import AnyKey
from runtime.actor import Actor, Scope
from runtime.agents.declaration import Agent
from runtime.agents.service import documents, hold_audio
from runtime.agents.service.declaration import NoSuchAgent, agent_of
from runtime.agents.service.pipeline import VendorHealth
from runtime.agents.service.settings import Picked, parse_test_values
from runtime.auth import Authenticator, actor_of
from runtime.enums import KeyScope
from runtime.exceptions import NotFound
from runtime.kit.http import read_capped_body
from runtime.postgres import Session

NO_AGENT_HERE = "no agent {slug} here"

# A supervisor's key opens the words of an agent; the pipeline's key opens everything of it.
WordsKey = Annotated[Actor, Depends(Authenticator(KeyScope.pipeline, KeyScope.words))]
PipelineKey = Annotated[Actor, Depends(Authenticator(KeyScope.pipeline))]
# `talk`: whoever may mint the widget's token may read how it looks.
TalkKey = Annotated[Actor, Depends(Authenticator(KeyScope.talk))]
# The agent's app records its lines and publishes its documents; a person with the pipeline does too.
PublishingKey = Annotated[Actor, Depends(Authenticator(KeyScope.app, KeyScope.pipeline))]
# A worker asks with its fleet's key; a tenant's own worker with an app key.
WorkerKey = Annotated[Actor, Depends(Authenticator(KeyScope.app, KeyScope.fleet))]
DeclarationKey = Annotated[Actor, Depends(Authenticator(KeyScope.app, KeyScope.calls, KeyScope.fleet))]


# ── what is handed in from above ──


# Whose a slug is, is whose its own log is: the first org to hold an agent claims its log, and the
# logs are `calls`', above this domain. Whatever keeps the claims is handed in under `agent_owners`.
class Owners(Protocol):
    """Who each agent belongs to."""

    async def owner(self, agent: str) -> str | None:
        """The org that claimed the agent's log, or None while nobody did."""
        ...


# Which app sockets hold an agent now is `live`'s, above this domain, handed in under `holders`.
class Holders(Protocol):
    """The apps holding each agent now."""

    def get_holder(self, scope: Scope, slug: str) -> object:
        """Whoever holds the agent in the scope, else in the org's own; refused when no app does."""
        ...


def owners_of(connection: HTTPConnection) -> Owners:
    """Who each agent belongs to, as the lifespan handed it in."""
    owners: Owners = connection.state.agent_owners
    return owners


def holders_of(connection: HTTPConnection) -> Holders:
    """The apps holding each agent now, as the lifespan handed them in."""
    holders: Holders = connection.state.holders
    return holders


def vendor_health_of(connection: HTTPConnection) -> VendorHealth:
    """The vendors failing now, as the lifespan handed their count in."""
    health: VendorHealth = connection.state.vendor_health
    return health


TheOwners = Annotated[Owners, Depends(owners_of)]
TheHolders = Annotated[Holders, Depends(holders_of)]
TheVendorHealth = Annotated[VendorHealth, Depends(vendor_health_of)]


# ── the agent of a path ──


# A slug typed wrong answered a plausible empty page before; another org's slug is the same 404. A
# request with no key passes: the endpoint's own key is what answers it 401.
async def the_known_agent(slug: str, request: Request, owners: TheOwners) -> str:
    """The path's agent, one the key's org has: held now, or held once. Any other slug is 404."""
    actor = actor_of(request)
    if actor is None or await owners.owner(slug) == actor.org:
        return slug
    raise NoSuchAgent(slug)


KnownAgent = Annotated[str, Depends(the_known_agent)]


async def the_known_filter(
    request: Request, owners: TheOwners, agent: Annotated[str | None, Query()] = None
) -> str | None:
    """A list's `?agent=`: none is every agent; one the org never held is 404, never an empty page."""
    return None if agent is None else await the_known_agent(agent, request, owners)


KnownFilter = Annotated[str | None, Depends(the_known_filter)]


# Any key reads the scope here; the endpoint's own key says what it opens.
async def the_agent(slug: KnownAgent, actor: AnyKey, session: Session) -> Agent:
    """The path's agent, the org's own, with what its class declares in the key's scope."""
    return await agent_of(session, actor.scope, slug)


TheAgent = Annotated[Agent, Depends(the_agent)]


# Another org's agent is the same 404 as nobody's: its existence does not leak.
async def the_held_agent(agent: TheAgent, actor: AnyKey, holders: TheHolders) -> Agent:
    """The path's agent, once an app holds it in the key's scope; refused when none does."""
    holders.get_holder(actor.scope, agent.slug)
    return agent


TheHeldAgent = Annotated[Agent, Depends(the_held_agent)]


# No key: the agent's org is the one its log belongs to; a slug nobody holds is 404.
async def owner_of_agent(slug: str, owners: TheOwners) -> str:
    """The org a published agent belongs to, for a page that reads it with no key."""
    org = await owners.owner(slug)
    if org is None:
        raise NotFound(NO_AGENT_HERE.format(slug=slug))
    return org


TheOwner = Annotated[str, Depends(owner_of_agent)]


# ── what a request reads ──


# A worker names the call it asks for before opening it (`for_call`: `call` would ask to act in an
# opened call's scope), so a canary's share is picked by the call's id; a worker that names none
# (an older one) is answered the version every call off the canary runs.
def read_picked(for_call: Annotated[str | None, Query()] = None) -> Picked:
    """Which call a worker asks for, so a canary's share is picked by its id."""
    return Picked(call=for_call)


ThePicked = Annotated[Picked, Depends(read_picked)]


def read_test_values(actor: AnyKey, test: Annotated[str | None, Query()] = None) -> dict[str, Any]:
    """A test room's own values as the worker says them back, checked again for the key's env."""
    return parse_test_values(test, env=actor.env)


TheTestValues = Annotated[dict[str, Any], Depends(read_test_values)]


# The body is the file, no multipart; the name rides the query.
async def read_melody(request: Request) -> bytes:
    """An uploaded melody, read up to what one may weigh."""
    return await read_capped_body(request, hold_audio.LONGEST_UPLOAD, "a hold melody as uploaded")


TheMelody = Annotated[bytes, Depends(read_melody)]


async def read_document(request: Request) -> bytes:
    """A document's body, read up to what one may weigh."""
    return await read_capped_body(request, documents.LARGEST, "a published document")


TheDocument = Annotated[bytes, Depends(read_document)]
