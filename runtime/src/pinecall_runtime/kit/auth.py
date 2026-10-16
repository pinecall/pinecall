"""Who a request is: the actor, and the dependency that requires its scopes."""

from collections.abc import Awaitable, Callable, Iterable
from dataclasses import dataclass
from datetime import datetime
from hmac import compare_digest

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from starlette.requests import HTTPConnection
from starlette.types import ASGIApp, Receive, Send
from starlette.types import Scope as ASGIScope

from pinecall_runtime.enums import Env, KeyScope, Role
from pinecall_runtime.exceptions import Forbidden, Unauthorized
from pinecall_runtime.kit.handles import handles_of

# The header a person's key names the env it acts in with; a server's key is its own env.
ENV_HEADER = "pinecall-env"
# An admin, in the sandbox, looking into a colleague's scope.
HOLDER_HEADER = "pinecall-corner"

# Holder value for org-owned rows: an empty string, not NULL, because it is part of primary keys.
THE_ORGS_OWN = ""


@dataclass(frozen=True, slots=True)
class Scope:
    """An org, one of its envs, and the holder a request acts as ("" for the org itself)."""

    org: str
    env: Env = Env.production
    holder: str = THE_ORGS_OWN


@dataclass(frozen=True, slots=True)
class Person:
    """The member a key was minted for, as its row stands now."""

    id: str
    org: str
    email: str
    name: str
    role: Role
    agents: frozenset[str] = frozenset()
    operator: bool = False
    production: bool = False

    @property
    def opens_production(self) -> bool:
        """Whether this person may act in production; admins always may."""
        return self.role is Role.admin or self.production


@dataclass(frozen=True, slots=True)
class Actor:
    """The verified key behind a request, its person, and the scope it acts in."""

    key_id: str
    org: str
    env: Env
    scopes: frozenset[KeyScope]
    person: Person | None = None
    label: str | None = None
    expires_at: datetime | None = None
    holder: str = THE_ORGS_OWN

    @property
    def scope(self) -> Scope:
        """The scope this actor acts in."""
        return Scope(self.org, self.env, self.holder)

    @property
    def is_server(self) -> bool:
        """A key with no person: a server's token, the fleet's or the runner's."""
        return self.person is None

    @property
    def name(self) -> str:
        """Who to write down as the author of a change."""
        return self.person.name if self.person else (self.label or self.key_id)

    def opens(self, *scopes: KeyScope) -> bool:
        """Whether the key holds any of the scopes."""
        return any(scope in self.scopes for scope in scopes)


def authorization_of(request: HTTPConnection) -> str | None:
    """The secret the Authorization header carries as a Bearer; never the URL, which lands in logs."""
    scheme, _, value = request.headers.get("authorization", "").partition(" ")
    return (value.strip() or None) if scheme.lower() == "bearer" else None


type Resolver = Callable[[HTTPConnection, AsyncSession], Awaitable[Actor | None]]


# Built before the lifespan opens the engine, so the sessions are found on the app per request.
class ActorMiddleware:
    """Resolves the request's actor once and keeps it on the request's state."""

    def __init__(self, app: ASGIApp, *, resolve: Resolver) -> None:
        self.app = app
        self.resolve = resolve

    async def __call__(self, scope: ASGIScope, receive: Receive, send: Send) -> None:
        """Resolve on http and websocket requests; pass everything else through."""
        if scope["type"] not in ("http", "websocket"):
            await self.app(scope, receive, send)
            return
        # A websocket's scope is no Request's (Starlette asserts http): both are connections.
        request = HTTPConnection(scope, receive)
        sessions: async_sessionmaker[AsyncSession] = request.app.state.sessions
        async with sessions() as session:
            scope.setdefault("state", {})["actor"] = await self.resolve(request, session)
        await self.app(scope, receive, send)


class Authenticator:
    """A dependency: the request's actor, holding one of the required scopes."""

    def __init__(self, *scopes: KeyScope, persons_only: bool = False) -> None:
        self.scopes: frozenset[KeyScope] = frozenset(scopes)
        self.persons_only = persons_only

    async def __call__(self, request: Request) -> Actor:
        """The actor; 401 without one, 403 without the scopes."""
        actor: Actor | None = getattr(request.state, "actor", None)
        if actor is None:
            raise Unauthorized("this endpoint takes an API key")
        if self.persons_only and actor.person is None:
            raise Forbidden("this endpoint is a person's: a server's token does not open it")
        if self.scopes and not actor.opens(*self.scopes):
            opens = " · ".join(sorted(actor.scopes)) or "nothing"
            wanted = " or ".join(sorted(self.scopes))
            raise Forbidden(f"this key does not open {wanted}: it opens {opens}")
        return actor


def actor_of(request: Request) -> Actor | None:
    """The actor the middleware resolved, or None on an anonymous request."""
    return getattr(request.state, "actor", None)


# The box's own key (PINECALL_OPS_KEY), which its billing and its terminal speak with: it names no
# person and acts for no org, so nothing it reads is scoped by row-level security.
THE_BOXS_KEY = "the box's key"


def the_box(request: Request) -> Actor | None:
    """The box itself, when the request carries PINECALL_OPS_KEY as its Bearer; None otherwise."""
    held = handles_of(request).settings.ops_key
    sent = authorization_of(request)
    if held is None or sent is None or not compare_digest(sent.encode(), held.get_secret_value().encode()):
        return None
    return Actor(key_id=THE_BOXS_KEY, org="", env=Env.production, scopes=frozenset(), label=THE_BOXS_KEY)


async def the_operator(request: Request) -> Actor:
    """The box's own key, or an actor whose person is one of the box's operators; 401 or 403 otherwise."""
    box = the_box(request)
    if box is not None:
        return box
    actor = await Authenticator(persons_only=True)(request)
    if actor.person is None or not actor.person.operator:
        raise Forbidden("this endpoint is the box's operator's")
    return actor


def person_of(actor: Actor) -> Person:
    """The person behind the actor; Forbidden for a server's token."""
    if actor.person is None:
        raise Forbidden("this endpoint is a person's: a server's token does not open it")
    return actor.person


def check_scopes(actor: Actor, scopes: Iterable[KeyScope]) -> None:
    """Forbidden unless the actor opens one of the scopes; for checks a dependency cannot express."""
    wanted = tuple(scopes)
    if wanted and not actor.opens(*wanted):
        opens = " · ".join(sorted(actor.scopes)) or "nothing"
        raise Forbidden(f"this key does not open {' or '.join(sorted(wanted))}: it opens {opens}")
