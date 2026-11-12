"""A visitor's way in: a browser's room token, a conversation resumed, a code a caller keys and its page asks after."""

import time
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, Literal

from sqlalchemy.ext.asyncio import AsyncSession

from runtime.accounts import service as accounts
from runtime.actor import Actor, Scope
from runtime.agents import service as agents
from runtime.calls import service as calls
from runtime.calls.context import Contact, new_call_id
from runtime.enums import Channel, KeyScope
from runtime.exceptions import Conflict, Forbidden, NotFound, ServiceUnavailable, ValidationError
from runtime.fleet import service as fleet
from runtime.kit.text import Json
from runtime.live.parts import LiveParts
from runtime.live.service import openings, tokens
from runtime.live.service.codes import Codes, NoSuchCode
from runtime.livekit import rooms_with_an_agent
from runtime.telephony import service as telephony
from runtime.wire.dispatch import Dispatch
from runtime.wire.events import FleetFull
from runtime.wire.parts import Projection
from runtime.wire.room import RoomScope

OURS_TO_SET = {
    "room_name": "the room is the call id this endpoint mints",
    "participant_name": "a name is PII, and the log would carry it",
    "participant_metadata": "it carries the contact id: send `contact`",
}
OUR_ATTRIBUTES = "pinecall."

# A key may seat a visitor for a day at most.
LONGEST_VISIT_TTL_S = 24 * 60 * 60
# 25 s: under the 30 s a proxy lets a request idle.
LONGEST_WAIT_S = 25.0
A_PAGE_MAY_ASK_AFTER_S = 60.0


class FleetIsFull(ServiceUnavailable):
    """Every slot of the fleet is taken."""

    def __init__(self, active: int, workers: int) -> None:
        super().__init__(
            f"every seat of the fleet is taken: {active} calls on {workers} workers. Offer a call back, or try "
            f"again in a minute"
        )


@dataclass(frozen=True, slots=True)
class Mint:
    """What a room token is asked for: livekit's own token request, and ours beside it."""

    agent: str | None = None
    scope: str = "talk"
    # An opaque contact id; never a number or a name.
    contact: str | None = None
    # Reaches the worker inside the signed dispatch: the browser reads it, never changes it.
    metadata: Mapping[str, Json] = field(default_factory=dict[str, Json])
    # A test room's own voice and models, over the agent's settings for this call alone.
    test_values: Mapping[str, Any] | None = None
    ttl_s: int | None = None
    log: Projection = "public"
    participant_identity: str | None = None
    participant_attributes: Mapping[str, str] = field(default_factory=dict[str, str])
    room_config: Mapping[str, object] | None = None
    # An earlier answer's resume token: back into that call while it waits, else one carrying it on.
    resume: str | None = None
    # Named so they are refused with the reason instead of as an unknown key.
    room_name: str | None = None
    participant_name: str | None = None
    participant_metadata: str | None = None


@dataclass(frozen=True, slots=True)
class Minted:
    """A room token minted: where the room is, the token, the call it opens, and the tokens that read and resume it."""

    server_url: str
    participant_token: str
    call: str
    log_token: str
    resume_token: str


@dataclass(frozen=True, slots=True)
class Earlier:
    """The call a mint resumes: whose it is, who called, and whether its room still waits."""

    call: str
    agent: str
    caller: str
    contact: Contact | None
    waiting: bool


@dataclass(frozen=True, slots=True)
class CodeToKey:
    """A code issued: the digits, the number to call, until when, and the token its page asks with."""

    code: str
    number: str
    expires_at: float
    code_token: str


@dataclass(frozen=True, slots=True)
class CodeStatus:
    """How a code stands; claimed, it names the call and a token that reads it."""

    code: str
    status: Literal["waiting", "claimed", "expired"]
    expires_at: float
    call: str | None = None
    log_token: str | None = None


# 201, livekit's own: a client SDK's token source expects it. The ledger row is written first, so
# the dispatch spends the token once.
async def mint_room_token(
    session: AsyncSession, live: LiveParts, signer: tokens.Signer, roster: fleet.Roster, actor: Actor, wanted: Mint
) -> Minted:
    """A room token for one of the key's agents: a new call, or one resumed."""
    _refuse_what_is_ours(wanted)
    org_scope = actor.scope
    scope = _read_visit_scope(wanted.scope)
    earlier = None if wanted.resume is None else await _get_earlier(session, live, signer, org_scope, wanted)
    if earlier is not None:
        accounts.check_agent(actor, earlier.agent)
    if earlier is not None and earlier.waiting:
        return _seat_again(live, signer, org_scope, scope, wanted, earlier)
    named = wanted.agent or (None if earlier is None else earlier.agent)
    agent = named or fleet.client_named_agent(wanted.room_config)
    if agent is None:
        raise ValidationError("name the agent: `agent` in the body, or agentName as a livekit client sends it")
    accounts.check_agent(actor, agent)
    if live.holders.find_serving(org_scope, agent) is None:
        raise NotFound(f"no app holds agent {agent}: start one, or deploy it")
    the_fleet = await fleet.fleet_of_env(session, org_scope.env)
    await _check_room_for_one_more(session, live, roster, the_fleet, agent)
    await openings.admit(session, live, org_scope, agent)
    call = new_call_id()
    expires_at = time.time() + min(wanted.ttl_s or tokens.ONE_VISIT_TTL_S, LONGEST_VISIT_TTL_S)
    visitor = wanted.participant_identity or _caller_of(earlier) or f"web_{new_call_id()[5:17]}"
    carried = Dispatch(
        agent=agent,
        org=org_scope.org,
        env=org_scope.env,
        holder=org_scope.holder or None,
        scope=scope,
        caller=visitor,
        contact=wanted.contact or _contact_of(earlier),
        metadata=dict(wanted.metadata),
        continues=None if earlier is None else earlier.call,
        # The dispatch's test values, under the word the wire carries them by.
        tuning=_check_test_values(wanted, actor),
    )
    seated = tokens.Visitor(
        expires_at=expires_at,
        identity=visitor,
        dispatch=fleet.room_dispatch(the_fleet, carried),
        attributes=wanted.participant_attributes,
        metadata=carried.contact,
    )
    token = tokens.sign_room_token(signer, call, scope, seated)
    await tokens.keep_token(session, call, org_scope, agent, scope, expires_at)
    return Minted(
        server_url=live.settings.browser_livekit_url(org_scope.env),
        participant_token=token,
        call=call,
        log_token=tokens.sign_log_token(signer, call, wanted.log, viewer=visitor),
        resume_token=tokens.sign_resume_token(signer, call),
    )


# The number is the key's own agent's in the key's env: a key issues codes for its agents.
async def issue_code(
    session: AsyncSession, codes: Codes, signer: tokens.Signer, actor: Actor, agent: str, ttl_s: float, log: Projection
) -> CodeToKey:
    """Four digits for a caller to key, the number to call, and a token that asks after them."""
    accounts.check_agent(actor, agent)
    routes = await telephony.list_phone_routes(session, actor.scope, agent=agent)
    if not routes:
        raise Conflict(f"agent {agent} answers at no phone number in {actor.env}: import one first")
    issued = await codes.issue(session, actor.env, agent, ttl_s, log)
    # The token outlives the code a little, so the page is told it expired rather than refused.
    asks_until = issued.expires_at + A_PAGE_MAY_ASK_AFTER_S
    token = tokens.sign_code_token(signer, issued.code, agent, actor.env, asks_until)
    return CodeToKey(code=issued.code, number=routes[0].number, expires_at=issued.expires_at, code_token=token)


# A page holds no key: the code token its page was handed is the only credential. Nothing here takes
# the request's session: a page that waits holds no connection while it does (`Codes.wait_for_claim`).
async def get_code_status(
    codes: Codes, signer: tokens.Signer, visit: tokens.Visit | None, code: str, *, wait: bool
) -> CodeStatus:
    """How the code stands; with wait, held up to 25 s for a call to key it."""
    if visit is None or visit.code != code or visit.agent is None or visit.env is None:
        raise Forbidden("this token reads another code")
    issued = await codes.find_status(visit.env, visit.agent, code)
    if issued is None:
        raise NoSuchCode(code, visit.agent)
    left = issued.expires_at - time.time()
    if wait and issued.claimed is None and left > 0:
        issued = await codes.wait_for_claim(issued, min(LONGEST_WAIT_S, left))
    if issued.claimed is not None:
        token = tokens.sign_log_token(signer, issued.claimed, issued.log)
        return CodeStatus(code, "claimed", issued.expires_at, call=issued.claimed, log_token=token)
    return CodeStatus(code, "expired" if time.time() >= issued.expires_at else "waiting", issued.expires_at)


# A test room's own voice and models are what the key that edits the pipeline may try, in the sandbox.
def _check_test_values(wanted: Mint, actor: Actor) -> dict[str, Any]:
    if not wanted.test_values:
        return {}
    if KeyScope.pipeline not in actor.scopes:
        raise Forbidden("a key that opens `pipeline` tries another voice or model in a test room")
    return agents.check_test_values(wanted.test_values, env=actor.env)


# A gateway nobody's worker reported to refuses nobody.
async def _check_room_for_one_more(
    session: AsyncSession, live: LiveParts, roster: fleet.Roster, the_fleet: str, agent: str
) -> None:
    totals = await fleet.totals_of(session, roster, the_fleet, time.time())
    if not totals.full:
        return
    full = FleetFull(channel=Channel.web, workers=totals.workers, active=totals.active)
    await live.logs.agent(agent).append("fleet.full", full.dump())
    raise FleetIsFull(totals.active, totals.workers)


def _refuse_what_is_ours(wanted: Mint) -> None:
    for field_name, sent in (
        ("room_name", wanted.room_name),
        ("participant_name", wanted.participant_name),
        ("participant_metadata", wanted.participant_metadata),
    ):
        if sent is not None:
            raise ValidationError(f"{field_name} is minted here and refused in the body: {OURS_TO_SET[field_name]}")
    if any(name.startswith(OUR_ATTRIBUTES) for name in wanted.participant_attributes):
        raise ValidationError(f"participant_attributes under {OUR_ATTRIBUTES} are minted here")


def _read_visit_scope(scope: str) -> RoomScope:
    for visit in tokens.MINTED_FOR_A_VISIT:
        if visit == scope:
            return visit
    raise ValidationError(
        f"scope is one of {sorted(tokens.MINTED_FOR_A_VISIT)}: observe and supervise take the API key instead"
    )


# The call is its org's and env's alone; a token of another's is refused as one nobody opened.
async def _get_earlier(
    session: AsyncSession, live: LiveParts, signer: tokens.Signer, org_scope: Scope, wanted: Mint
) -> Earlier:
    call = None if wanted.resume is None else tokens.read_resume_token(signer, wanted.resume)
    if call is None:
        raise Forbidden("resume is not a resume token of this gateway's, or it expired: start a new conversation")
    kept = await calls.find_head(session, call)
    opening = await calls.opening_of(session, call)
    if kept is None or kept.scope != org_scope or opening is None:
        raise NotFound(f"call {call} was not opened by this key's org and env: it cannot be resumed")
    if wanted.agent is not None and wanted.agent != kept.agent:
        raise ValidationError(
            f"call {call} is agent {kept.agent}'s, not {wanted.agent}'s: resume it with its own agent"
        )
    waiting = not kept.sealed and call in await rooms_with_an_agent(live.servers[org_scope.env], [call])
    context = opening.context
    return Earlier(call, kept.agent, context.caller, context.contact, waiting)


# The agent is still in the room, waiting for the visitor: they sit back down as who they were,
# and the call goes on. No dispatch rides the token, so no second call can open from it.
def _seat_again(
    live: LiveParts, signer: tokens.Signer, org_scope: Scope, scope: RoomScope, wanted: Mint, earlier: Earlier
) -> Minted:
    ttl = min(wanted.ttl_s or tokens.ONE_VISIT_TTL_S, LONGEST_VISIT_TTL_S)
    seated = tokens.Visitor(
        expires_at=time.time() + ttl,
        identity=earlier.caller,
        attributes=wanted.participant_attributes,
        metadata=_contact_of(earlier),
    )
    return Minted(
        server_url=live.settings.browser_livekit_url(org_scope.env),
        participant_token=tokens.sign_room_token(signer, earlier.call, scope, seated),
        call=earlier.call,
        log_token=tokens.sign_log_token(signer, earlier.call, wanted.log, viewer=earlier.caller),
        resume_token=tokens.sign_resume_token(signer, earlier.call),
    )


def _caller_of(earlier: Earlier | None) -> str | None:
    return None if earlier is None else earlier.caller


def _contact_of(earlier: Earlier | None) -> str | None:
    return None if earlier is None or earlier.contact is None else earlier.contact.id
