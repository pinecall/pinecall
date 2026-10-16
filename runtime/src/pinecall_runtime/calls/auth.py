"""Who may call the call endpoints: a key in its scope, the fleet's, or a token of one call."""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.requests import HTTPConnection

from pinecall_runtime.accounts.service import keys, tokens
from pinecall_runtime.agents.declaration import AgentConfig
from pinecall_runtime.calls.repository.heads import HeadRepository
from pinecall_runtime.calls.service.live import Served
from pinecall_runtime.calls.service.serving import NO_SUCH_CALL, Serving, get_served, is_the_fleet
from pinecall_runtime.compliance import service as compliance
from pinecall_runtime.enums import KeyScope, ReadKind
from pinecall_runtime.exceptions import Forbidden, NotFound, Unauthorized
from pinecall_runtime.kit import jwt
from pinecall_runtime.kit.auth import Actor, Authenticator, Scope, actor_of, authorization_of, the_operator
from pinecall_runtime.postgres import Session
from pinecall_runtime.wire.parts import Projection

READ_WITH_A_KEY = "a log is read with a key, or with a token of that call"
NOT_YOURS = "this token reads another call"
NEVER_OPENED = "no call {call} was opened: the fleet's key reads and acts for a call once it is"

# A worker asks with its fleet's key; a tenant's own worker with an app key.
WorkerKey = Annotated[Actor, Depends(Authenticator(KeyScope.app, KeyScope.fleet))]
FleetKey = Annotated[Actor, Depends(Authenticator(KeyScope.fleet))]
TalkKey = Annotated[Actor, Depends(Authenticator(KeyScope.talk))]
KnowledgeKey = Annotated[Actor, Depends(Authenticator(KeyScope.knowledge))]
MemoryKey = Annotated[Actor, Depends(Authenticator(KeyScope.memory))]
EvalsKey = Annotated[Actor, Depends(Authenticator(KeyScope.evals))]
CallsKey = Annotated[Actor, Depends(Authenticator(KeyScope.calls))]
TeamKey = Annotated[Actor, Depends(Authenticator(KeyScope.team))]
UsageKey = Annotated[Actor, Depends(Authenticator(KeyScope.usage))]
SuperviseKey = Annotated[Actor, Depends(Authenticator(KeyScope.supervise))]
AppKey = Annotated[Actor, Depends(Authenticator(KeyScope.app))]
TheOperator = Annotated[Actor, Depends(the_operator)]


@dataclass(frozen=True)
class Reader:
    """Who reads a log: a key in its scope, or a token of one call."""

    actor: Actor | None = None
    visit: tokens.Visit | None = None

    @property
    def scope(self) -> Scope | None:
        """The scope a key reads in; None for a token, or the fleet, which serves every org."""
        if self.actor is None or is_the_fleet(self.actor):
            return None
        return self.actor.scope

    @property
    def projection(self) -> Projection:
        """What the reader sees of an entry: a key sees the tenant's, a token its own grant's."""
        return "tenant" if self.visit is None else self.visit.effective_projection

    @property
    def viewer(self) -> str | None:
        """The identity a token's holder watches as; None for a key."""
        return None if self.visit is None else self.visit.identity


def serving_of(connection: HTTPConnection) -> Serving:
    """What the lifespan built to serve calls."""
    serving: Serving = connection.app.state.serving
    return serving


TheServing = Annotated[Serving, Depends(serving_of)]


# ?token= only for a token of ours: EventSource sets no header, and a key in a URL would leak.
# A worker reads the call it serves with the fleet's key and names no scope to do it, since the
# call's head row says whose it is: only a call's own reading endpoints (its events, its state,
# its recording) let that key in.
def reading(*opens: KeyScope) -> Callable[..., Awaitable[Reader]]:
    """A dependency that lets through a key that opens one of the scopes, or a call's token."""

    async def read(request: Request, token: Annotated[str | None, Query()] = None) -> Reader:
        data = authorization_of(request) or token
        if data is None:
            raise Unauthorized(READ_WITH_A_KEY)
        if jwt.is_a_jwt(data):
            visit = tokens.read_token(serving_of(request).signer, data)
            if visit is None:
                raise Unauthorized(READ_WITH_A_KEY)
            return Reader(visit=visit)
        actor = actor_of(request)
        if actor is None:
            raise Unauthorized(READ_WITH_A_KEY)
        if opens and not actor.opens(*opens):
            raise Forbidden(f"this key does not open {' or '.join(sorted(opens))}")
        _check_agent_named(request, actor)
        return Reader(actor=actor)

    return read


ReaderDep = Annotated[Reader, Depends(reading(KeyScope.calls))]
CallReaderDep = Annotated[Reader, Depends(reading(KeyScope.calls, KeyScope.fleet))]


# The call as this gateway serves it, for the worker that opened it: one dependency, so an
# endpoint of the worker's is the service call and nothing else.
async def served_call(call: str, actor: WorkerKey, serving: TheServing, session: Session) -> Served:
    """The call named in the path, served here, as its opener's key may reach it."""
    return await get_served(session, serving, actor, call)


# The lookup is any key's of the call's org and env, the fleet's included: an app searches its
# knowledge on a call it serves whoever opened it.
async def served_call_of_anyone(call: str, actor: WorkerKey, serving: TheServing, session: Session) -> Served:
    """The call named in the path, served here, for a key of its org and env."""
    return await get_served(session, serving, actor, call, openers=False)


TheServedCall = Annotated[Served, Depends(served_call)]
AnyonesServedCall = Annotated[Served, Depends(served_call_of_anyone)]


# A key reads a call of its org in its env; a token, its own call alone. A call nobody wrote
# yet is empty to a key, not another org's: a client that minted the id tails it before the room
# opens. The fleet's key reads only a call that was opened, of the env it serves.
async def check_readable(session: AsyncSession, serving: Serving, reader: Reader, call: str) -> AgentConfig | None:
    """Refuse a reader the call is not theirs; the declaration of its agent, when held."""
    if reader.visit is not None and reader.visit.call != call:
        raise Forbidden(NOT_YOURS)
    kept = await HeadRepository(session).head_of_call(call)
    fleet = reader.actor is not None and is_the_fleet(reader.actor)
    if fleet and (kept is None or kept.scope is None):
        raise NotFound(NEVER_OPENED.format(call=call))
    if kept is None:
        return None
    if not _sees(reader, kept.scope):
        raise NotFound(NO_SUCH_CALL.format(call=call))
    if reader.actor is not None:
        keys.check_agent(reader.actor, kept.agent)
    return serving.registry.declared(kept.agent)


# A person's read and a server's are written down, by the person or the key; a visitor reads
# its own call and the fleet the call it serves, neither of which is an access to record.
async def record_read(session: AsyncSession, reader: Reader, call: str, what: ReadKind) -> None:
    """Write down who read the call, and what of it."""
    scope = reader.scope
    if reader.actor is None or scope is None:
        return
    await compliance.record_read(session, scope, call, what, by=asked_by(reader.actor))


def asked_by(actor: Actor) -> str:
    """The person behind the key, or the key itself for a server's."""
    return actor.person.id if actor.person is not None else actor.key_id


# The org's own calls and the reader's own scope; a token is checked by its call, the fleet's
# key reads the calls of the env it serves and none of the other.
def _sees(reader: Reader, owner: Scope | None) -> bool:
    if reader.visit is not None:
        return True
    if reader.actor is not None and is_the_fleet(reader.actor):
        return owner is not None and owner.env is reader.actor.env
    mine = reader.scope
    if mine is None or owner is None:
        return False
    same = mine.org == owner.org and mine.env is owner.env
    return same and owner.holder in ("", mine.holder)


# The agent an endpoint names in its path or its query; a body's agent is checked by its endpoint.
def _check_agent_named(request: Request, actor: Actor) -> None:
    for slug in (request.path_params.get("slug"), request.query_params.get("agent")):
        if slug:
            keys.check_agent(actor, slug)
