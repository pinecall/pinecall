"""The tokens the gateway signs: a room token, a seat, a log token, a code token, a resume token."""

import time
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import timedelta
from typing import Literal

import jwt
from livekit.api import AccessToken, VideoGrants
from livekit.protocol.room import RoomConfiguration
from pydantic import BaseModel, ConfigDict, Field
from pydantic import ValidationError as PydanticValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from pinecall_runtime.accounts.models import Token
from pinecall_runtime.accounts.repository import TokenRepository
from pinecall_runtime.enums import Env
from pinecall_runtime.kit.auth import Actor, Scope
from pinecall_runtime.kit.crypto import random_id
from pinecall_runtime.wire.parts import Projection

# A room token's scope rides the seat as a LiveKit attribute, so the worker reads it without a lookup.
type RoomScope = Literal["talk", "chat", "observe", "supervise", "participate", "read"]
type Spending = Literal["spent", "already_spent", "never_minted", "minted_elsewhere"]

SCOPE_ATTRIBUTE = "pinecall.scope"
SUBJECT_ATTRIBUTE = "pinecall.subject"
NAME_ATTRIBUTE = "pinecall.name"
PROJECTION_ATTRIBUTE = "pinecall.projection"
CODE_ATTRIBUTE = "pinecall.code"
AGENT_ATTRIBUTE = "pinecall.agent"
ENV_ATTRIBUTE = "pinecall.env"

A_VISITOR = "web_"
A_SEAT = "sup_"
THE_MICROPHONE = "microphone"
# The header of a token the gateway signs with its own key; a LiveKit token names no key id.
OUR_KEY_ID = "pinecall"

ONE_VISIT_TTL_S = 60
A_SEAT_LASTS_S = 15 * 60
READ_TTL_S = 4 * 60 * 60
RESUMES_FOR_S = 30 * 24 * 60 * 60


@dataclass(frozen=True, slots=True)
class Signer:
    """The LiveKit pair a room token is signed with, and the gateway's own key for every other."""

    api_key: str
    secret: str
    own: str


@dataclass(frozen=True, kw_only=True, slots=True)
class Grant:
    """What a room token of one scope may do."""

    connects: bool
    audio: bool
    reads_log: bool
    own_call_only: bool
    ttl_s: int | None
    hears: bool = False
    hidden: bool = False
    writes: bool = False


GRANTS: Mapping[RoomScope, Grant] = {
    "talk": Grant(connects=True, audio=True, writes=True, reads_log=True, own_call_only=True, ttl_s=ONE_VISIT_TTL_S),
    "chat": Grant(
        connects=True, audio=False, hears=True, writes=True, reads_log=True, own_call_only=True, ttl_s=ONE_VISIT_TTL_S
    ),
    "observe": Grant(
        connects=False, audio=False, hears=True, hidden=True, reads_log=True, own_call_only=False, ttl_s=None
    ),
    # Not hidden: livekit delivers no track of a hidden seat, so a takeover would be silent.
    "supervise": Grant(connects=False, audio=True, reads_log=True, own_call_only=False, ttl_s=None),
    "read": Grant(connects=False, audio=False, reads_log=True, own_call_only=True, ttl_s=READ_TTL_S),
    "participate": Grant(connects=False, audio=False, writes=True, reads_log=True, own_call_only=True, ttl_s=None),
}

# A scope that reads beyond its own call is the tenant's.
PROJECTION_OF: Mapping[RoomScope, Projection] = {
    scope: "tenant" if grant.reads_log and not grant.own_call_only else "public" for scope, grant in GRANTS.items()
}
MINTED_FOR_A_VISIT: frozenset[RoomScope] = frozenset(scope for scope, grant in GRANTS.items() if grant.connects)
_OWN_CALL: tuple[RoomScope, ...] = ("talk", "chat", "read", "participate")
READS_ITS_OWN_CALL: frozenset[RoomScope] = frozenset(_OWN_CALL)
_BOUND: tuple[RoomScope, ...] = (*_OWN_CALL, "supervise")
BOUND_TO_ONE_CALL: frozenset[RoomScope] = frozenset(_BOUND)


@dataclass(frozen=True, slots=True)
class Visitor:
    """Who a room token seats, until when, and the dispatch it carries."""

    expires_at: float
    identity: str | None = None
    subject: str | None = None
    name: str | None = None
    dispatch: RoomConfiguration | None = None


@dataclass(frozen=True, slots=True)
class Visit:
    """What a checked token says."""

    call: str
    scope: RoomScope
    expires_at: float
    identity: str | None = None
    subject: str | None = None
    name: str | None = None
    projection: Projection | None = None
    code: str | None = None
    agent: str | None = None
    env: Env | None = None

    @property
    def effective_projection(self) -> Projection:
        """The projection the token reads through."""
        return self.projection or PROJECTION_OF[self.scope]


@dataclass(frozen=True, slots=True)
class Seat:
    """A person's seat in a live call: the token and who it says they are."""

    call: str
    identity: str
    token: str
    subject: str | None
    name: str | None


class _Room(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore")
    room: str = ""


class _Attributes(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore")
    scope: RoomScope = Field(alias=SCOPE_ATTRIBUTE)
    subject: str | None = Field(None, alias=SUBJECT_ATTRIBUTE)
    name: str | None = Field(None, alias=NAME_ATTRIBUTE)
    projection: Projection | None = Field(None, alias=PROJECTION_ATTRIBUTE)
    code: str | None = Field(None, alias=CODE_ATTRIBUTE)
    agent: str | None = Field(None, alias=AGENT_ATTRIBUTE)
    env: Env | None = Field(None, alias=ENV_ATTRIBUTE)


class _Claims(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore")
    exp: float
    sub: str | None = None
    video: _Room = _Room()
    attributes: _Attributes


class _Resumes(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore")
    exp: float
    resumes: str


def room_token(signer: Signer, call: str, scope: RoomScope, visitor: Visitor) -> str:
    """A token that seats the visitor in the call's room with the scope's grants."""
    grant = GRANTS[scope]
    grants = VideoGrants(
        room=call,
        room_join=True,
        can_publish=grant.audio,
        can_subscribe=grant.audio or grant.hears,
        can_publish_data=grant.writes,
        can_publish_sources=[THE_MICROPHONE] if grant.audio else [],
        hidden=grant.hidden,
    )
    who = {a: v for a, v in ((SUBJECT_ATTRIBUTE, visitor.subject), (NAME_ATTRIBUTE, visitor.name)) if v}
    token = (
        AccessToken(signer.api_key, signer.secret)
        .with_identity(visitor.identity or random_id(A_VISITOR, 6))
        .with_grants(grants)
        .with_ttl(timedelta(seconds=visitor.expires_at - time.time()))
        .with_attributes({**who, SCOPE_ATTRIBUTE: scope})
    )
    if visitor.dispatch is not None:
        token = token.with_room_config(visitor.dispatch)
    return token.to_jwt()


def seat_token(signer: Signer, call: str, scope: RoomScope, actor: Actor) -> Seat:
    """A seat for the actor's person in a live call, to listen or to supervise."""
    identity = random_id(A_SEAT, 6)
    subject = None if actor.person is None else actor.person.id
    visitor = Visitor(expires_at=time.time() + A_SEAT_LASTS_S, identity=identity, subject=subject, name=actor.name)
    return Seat(call, identity, room_token(signer, call, scope, visitor), subject, actor.name)


def log_token(signer: Signer, call: str, projection: Projection) -> str:
    """A token that reads one call's log and recording through the projection; it opens no room."""
    return _unjoinable(signer, call, READ_TTL_S, {SCOPE_ATTRIBUTE: "read", PROJECTION_ATTRIBUTE: projection})


def code_token(signer: Signer, code: str, agent: str, env: Env, expires_at: float) -> str:
    """A token that asks after one caller code until the code dies."""
    attributes = {SCOPE_ATTRIBUTE: "read", CODE_ATTRIBUTE: code, AGENT_ATTRIBUTE: agent, ENV_ATTRIBUTE: env}
    return _unjoinable(signer, f"code:{code}", expires_at - time.time(), attributes)


def resume_token(signer: Signer, call: str) -> str:
    """A token that carries one call on; signed with the gateway's own key."""
    moment = int(time.time())
    return jwt.encode(
        {"iat": moment, "exp": moment + RESUMES_FOR_S, "resumes": call},
        signer.own,
        algorithm="HS256",
        headers={"kid": OUR_KEY_ID},
    )


def resumed_call(signer: Signer, token: str) -> str | None:
    """The call a resume token carries on; None for any other token, or one expired."""
    try:
        decoded = jwt.decode(token, signer.own, algorithms=["HS256"], options={"require": ["exp"]}, leeway=0)
        return _Resumes.model_validate(decoded).resumes
    except (jwt.PyJWTError, PydanticValidationError):
        return None


def read_token(signer: Signer, token: str) -> Visit | None:
    """What a token of ours says; None for anything else, whatever the reason."""
    try:
        ours = jwt.get_unverified_header(token).get("kid") == OUR_KEY_ID
        decoded = jwt.decode(
            token, signer.own if ours else signer.secret, algorithms=["HS256"], options={"require": ["exp"]}, leeway=0
        )
        claims = _Claims.model_validate(decoded)
    except (jwt.PyJWTError, PydanticValidationError):
        return None
    data = claims.attributes
    # A reading token is the gateway's own key's alone: one in its shape under the pair is a forgery.
    if not claims.video.room or data.scope not in BOUND_TO_ONE_CALL or ours != (data.scope == "read"):
        return None
    return Visit(
        call="" if data.code is not None else claims.video.room,
        scope=data.scope,
        expires_at=claims.exp,
        identity=claims.sub,
        subject=data.subject,
        name=data.name,
        projection=data.projection,
        code=data.code,
        agent=data.agent,
        env=data.env,
    )


async def record_minted(
    session: AsyncSession, call: str, scope: Scope, agent: str, room_scope: RoomScope, expires_at: float
) -> None:
    """Keep a room token the ledger will spend once, when its call opens."""
    from datetime import UTC, datetime

    await TokenRepository(session).add(
        Token(
            call=call,
            org=scope.org,
            env=scope.env,
            agent=agent,
            scope=room_scope,
            expires_at=datetime.fromtimestamp(expires_at, UTC),
        )
    )


async def spend_token(session: AsyncSession, call: str, scope: Scope, agent: str) -> Spending:
    """Spend the call's token in the scope the worker names, once; otherwise say why not."""
    tokens = TokenRepository(session)
    if await tokens.spend(call, scope.org, scope.env, agent):
        return "spent"
    row = await tokens.get(call)
    if row is None:
        return "never_minted"
    return "minted_elsewhere" if row.spent_at is None else "already_spent"


def _unjoinable(signer: Signer, room: str, ttl_s: float, attributes: dict[str, str]) -> str:
    moment = int(time.time())
    claims = {
        "sub": random_id(A_VISITOR, 6),
        "iat": moment,
        "exp": moment + int(ttl_s),
        "video": {"room": room, "roomJoin": False},
        "attributes": attributes,
    }
    return jwt.encode(claims, signer.own, algorithm="HS256", headers={"kid": OUR_KEY_ID})
