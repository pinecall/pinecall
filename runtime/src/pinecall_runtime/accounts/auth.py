"""Who may call the accounts endpoints, how a request's actor is resolved, and what the endpoints reach for."""

from dataclasses import replace
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.requests import HTTPConnection

from pinecall_runtime.accounts.repository import MemberRepository
from pinecall_runtime.accounts.service import keys
from pinecall_runtime.accounts.service.keys import KeyCache
from pinecall_runtime.accounts.service.mail import Outbox
from pinecall_runtime.accounts.service.signin import Pairings, SignIns, SignUps
from pinecall_runtime.accounts.service.turnstile import Turnstile
from pinecall_runtime.enums import Env, KeyScope
from pinecall_runtime.exceptions import NotFound
from pinecall_runtime.kit import jwt as tokens
from pinecall_runtime.kit.auth import (
    ENV_HEADER,
    HOLDER_HEADER,
    THE_ORGS_OWN,
    Actor,
    Authenticator,
    Person,
    Scope,
    authorization_of,
    person_of,
    the_operator,
)
from pinecall_runtime.kit.handles import handles_of
from pinecall_runtime.platform import service as platform
from pinecall_runtime.postgres import Session, scope_to


async def resolve_actor(request: HTTPConnection, session: AsyncSession) -> Actor | None:
    """The actor behind the request's key, in the env and scope it asks for; None without a key."""
    secret = authorization_of(request)
    if secret is None or tokens.is_a_jwt(secret):
        return None
    cache: keys.KeyCache = request.app.state.key_cache
    verified = await cache.verify(secret)
    if verified is None:
        return None
    key, member = verified
    env = keys.env_of_request(key, member, request.headers.get(ENV_HEADER))
    actor = keys.actor_of(key, member, env)
    looking_at = request.headers.get(HOLDER_HEADER)
    colleague = await MemberRepository(session).get(actor.org, looking_at) if looking_at else None
    scope = keys.scope_of_request(actor, colleague)
    # Every transaction of this request acts for the key's org (row-level security); the fleet's
    # and the runner's keys serve every org of an env, so theirs act as the box.
    if not actor.opens(KeyScope.fleet, KeyScope.runner):
        scope_to(actor.org)
    resolved = keys.actor_of(key, member, env, holder=scope.holder)
    dispatched = dispatched_scope(request) if actor.opens(KeyScope.fleet) else None
    if dispatched is None:
        return resolved
    return replace(resolved, org=dispatched.org, env=dispatched.env, holder=dispatched.holder)


# Only the fleet's key names a scope: the scope of the call it serves, as its dispatch named it
# (`?org=&env=&holder=`). Its own org is the box's and holds none of the calls it answers.
def dispatched_scope(request: HTTPConnection) -> Scope | None:
    """The scope a worker asks in, from the dispatch it was started with; None when it names none."""
    org, env = request.query_params.get("org"), request.query_params.get("env")
    if not org or env not in set(Env):
        return None
    return Scope(org, Env(env), request.query_params.get("holder") or THE_ORGS_OWN)


AnyKey = Annotated[Actor, Depends(Authenticator())]
PersonKey = Annotated[Actor, Depends(Authenticator(persons_only=True))]
TeamKey = Annotated[Actor, Depends(Authenticator(KeyScope.team))]
AppKey = Annotated[Actor, Depends(Authenticator(KeyScope.app, persons_only=True))]
TheOperator = Annotated[Actor, Depends(the_operator)]


def the_person(actor: PersonKey) -> Person:
    """The person behind a person's key."""
    return person_of(actor)


ThePerson = Annotated[Person, Depends(the_person)]


# ── what the endpoints reach for on the app's state ──


def sign_ins(request: Request) -> SignIns:
    """What sign-in keeps between requests."""
    kept: SignIns = request.app.state.sign_ins
    return kept


def outbox(request: Request) -> Outbox:
    """The gateway's outbox."""
    kept: Outbox = request.app.state.outbox
    return kept


def key_cache(request: Request) -> KeyCache:
    """The keys verified lately."""
    kept: KeyCache = request.app.state.key_cache
    return kept


def pairings(sign_ins_: "SignInsDep") -> Pairings:
    """The terminals waiting to be signed in."""
    return Pairings(sign_ins_.pairings, sign_ins_.signal)


def sign_ups(sign_ins_: "SignInsDep") -> SignUps:
    """The sign-ups waiting for their code."""
    return SignUps(sign_ins_.signups)


def client_of(request: Request) -> str:
    """The address a request came from, as the throttle counts it."""
    return request.client.host if request.client is not None else "unknown"


def public_url(request: Request) -> str:
    """The box's address, else the one the request came in by: never a forged Host where the box has a name."""
    return handles_of(request).settings.address or str(request.base_url).rstrip("/")


def min_password(request: Request) -> int:
    """The box's floor for a password."""
    return handles_of(request).settings.min_password


def turnstile_of(request: Request) -> Turnstile:
    """The box's Turnstile: Cloudflare's verifier where the operator set a secret, else one that passes all."""
    handles = handles_of(request)
    secret = handles.settings.turnstile_secret
    return Turnstile(handles.http, None if secret is None else secret.get_secret_value(), handles.settings.domain)


async def brand_of(session: Session) -> platform.Brand:
    """The box's brand."""
    return await platform.get_brand(session)


SignInsDep = Annotated[SignIns, Depends(sign_ins)]
OutboxDep = Annotated[Outbox, Depends(outbox)]
KeyCacheDep = Annotated[KeyCache, Depends(key_cache)]
PairingsDep = Annotated[Pairings, Depends(pairings)]
SignUpsDep = Annotated[SignUps, Depends(sign_ups)]
BrandDep = Annotated[platform.Brand, Depends(brand_of)]
PublicUrl = Annotated[str, Depends(public_url)]
Client = Annotated[str, Depends(client_of)]
MinPassword = Annotated[int, Depends(min_password)]
TurnstileDep = Annotated[Turnstile, Depends(turnstile_of)]


def signup_client(request: Request) -> str:
    """The address a sign-up is counted by; refused where sign-ups are shut."""
    if not handles_of(request).settings.signup:
        raise NotFound(
            "sign-ups are not open on this box: its operator sets PINECALL_SIGNUP, or makes the org and invites you"
        )
    return client_of(request)


SignupClient = Annotated[str, Depends(signup_client)]
