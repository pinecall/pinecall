"""Accounts' dependencies: a request's actor resolved, the keys that open its endpoints, its loaders and getters."""

from typing import Annotated

from fastapi import Depends, Path, Request
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.requests import HTTPConnection

from runtime.accounts.models import Org
from runtime.accounts.repository.members import Membership
from runtime.accounts.service import members, orgs
from runtime.accounts.service.actor import Asked, read_dispatch, resolve
from runtime.accounts.service.key_cache import KeyCache
from runtime.actor import Actor, Person
from runtime.auth import ENV_HEADER, HOLDER_HEADER, Authenticator, TheOperator, authorization_of, person_of
from runtime.enums import KeyScope
from runtime.handles import TheSettings, settings_of
from runtime.kit.text import is_a_jwt
from runtime.postgres import Session, TheBoxSession
from runtime.scoping import scope_to


def key_cache_of(connection: HTTPConnection) -> KeyCache:
    """The keys this gateway verified lately."""
    cache: KeyCache = connection.state.key_cache
    return cache


TheKeyCache = Annotated[KeyCache, Depends(key_cache_of)]


# What `ActorMiddleware` is given: the request read here, the resolution in `service/actor.py`.
async def resolve_actor(request: HTTPConnection, session: AsyncSession) -> Actor | None:
    """The actor behind the request's key, in the env and scope it asks for; None without a key."""
    secret = authorization_of(request)
    if secret is None or is_a_jwt(secret):
        return None
    verified = await key_cache_of(request).verify(secret)
    if verified is None:
        return None
    query, headers = request.query_params, request.headers
    dispatched = read_dispatch(query.get("org"), query.get("env"), query.get("holder"))
    asked = Asked(env=headers.get(ENV_HEADER), looking_at=headers.get(HOLDER_HEADER), dispatched=dispatched)
    actor = await resolve(session, verified, asked)
    # Every transaction of this request acts for the key's org (row-level security); the fleet's
    # and the runner's keys serve every org of an env, so theirs act as the box.
    if not actor.opens(KeyScope.fleet, KeyScope.runner):
        scope_to(actor.org)
    return actor


AnyKey = Annotated[Actor, Depends(Authenticator())]
PersonKey = Annotated[Actor, Depends(Authenticator(persons_only=True))]
TeamKey = Annotated[Actor, Depends(Authenticator(KeyScope.team))]
# `app`, held by a person: a server's token with `app` serves an agent and makes no key.
PersonsAppKey = Annotated[Actor, Depends(Authenticator(KeyScope.app, persons_only=True))]


def the_person(actor: PersonKey) -> Person:
    """The person behind a person's key."""
    return person_of(actor)


ThePerson = Annotated[Person, Depends(the_person)]


async def load_named_org(named: str, _actor: TheOperator, session: TheBoxSession) -> Org:
    """The org an operator's path names, by id or slug."""
    return await orgs.get_org(session, named)


TheNamedOrg = Annotated[Org, Depends(load_named_org)]

# The path says {id}, as the console spells it; `id` is a builtin, so the argument says member.
MemberId = Annotated[str, Path(alias="id")]


async def load_member(member_id: MemberId, actor: TeamKey, session: Session) -> Membership:
    """The member of the key's org a path names, with the person they are."""
    return await members.get_member(session, actor.org, member_id)


async def load_named_orgs_member(member_id: MemberId, org: TheNamedOrg, session: TheBoxSession) -> Membership:
    """The member an operator's path names, in the org it names."""
    return await members.get_member(session, org.id, member_id)


TheMember = Annotated[Membership, Depends(load_member)]
TheNamedOrgsMember = Annotated[Membership, Depends(load_named_orgs_member)]


def public_url_of(request: Request, settings: TheSettings) -> str:
    """The box's address, else the one the request came in by: never a forged Host where the box has a name."""
    return settings.address or str(request.base_url).rstrip("/")


def min_password_of(connection: HTTPConnection) -> int:
    """The box's floor for a password."""
    return settings_of(connection).min_password


PublicUrl = Annotated[str, Depends(public_url_of)]
MinPassword = Annotated[int, Depends(min_password_of)]
