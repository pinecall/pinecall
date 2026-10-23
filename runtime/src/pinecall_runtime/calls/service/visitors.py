"""A visitor's way in: a browser's room token, a conversation resumed, a code a caller keys."""

import time
from dataclasses import dataclass
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from pinecall_runtime.accounts.service import keys, tokens
from pinecall_runtime.agents.service import settings
from pinecall_runtime.alerts import service as alerts
from pinecall_runtime.billing import service as billing
from pinecall_runtime.calls.context import Contact, new_call_id
from pinecall_runtime.calls.repository.heads import HeadRepository
from pinecall_runtime.calls.schemas import (
    CodeStatus,
    IssueCodeRequest,
    IssueCodeResponse,
    MintTokenRequest,
    MintTokenResponse,
)
from pinecall_runtime.calls.service import openings
from pinecall_runtime.calls.service.serving import Serving
from pinecall_runtime.channels import service as channels
from pinecall_runtime.enums import Channel, KeyScope
from pinecall_runtime.exceptions import (
    Conflict,
    Forbidden,
    NotFound,
    QuotaExceeded,
    ServiceUnavailable,
    ValidationError,
)
from pinecall_runtime.fleet import service as fleet
from pinecall_runtime.kit.auth import Actor, Scope
from pinecall_runtime.wire.dispatch import Dispatch
from pinecall_runtime.wire.events import FleetFull

NO_AGENT_NAMED = "name the agent: `agent` in the body, or agentName as a livekit client sends it"
NO_AGENT = "no app holds agent {slug}: start one, or deploy it"
OURS_TO_SET = {
    "room_name": "the room is the call id this endpoint mints",
    "participant_name": "a name is PII, and the log would carry it",
    "participant_metadata": "it carries the contact id: send `contact`",
}
OUR_ATTRIBUTES = "pinecall."
NOT_A_RESUME = "resume is not a resume token of this gateway's, or it expired: start a new conversation"

# A key may seat a visitor for a day at most.
LONGEST_VISIT_TTL_S = 24 * 60 * 60
# 25 s: under the 30 s a proxy lets a request idle.
LONGEST_WAIT_S = 25.0
A_PAGE_MAY_ASK_AFTER_S = 60.0


class FleetIsFull(ServiceUnavailable):
    """Every seat of the fleet is taken."""

    def __init__(self, active: int, workers: int) -> None:
        super().__init__(
            f"every seat of the fleet is taken: {active} calls on {workers} workers. Offer a call back, or try "
            f"again in a minute"
        )


@dataclass(frozen=True)
class Earlier:
    """The call a mint resumes: whose it is, who called, and whether its room still waits."""

    call: str
    agent: str
    caller: str
    contact: Contact | None
    waiting: bool


# 201, livekit's own: a client SDK's token source expects it. The ledger row is written first, so
# the dispatch spends the token once.
async def mint_room_token(
    session: AsyncSession, serving: Serving, actor: Actor, body: MintTokenRequest
) -> MintTokenResponse:
    """A room token for one of the key's agents: a new call, or one resumed."""
    _refuse_what_is_ours(body)
    org_scope = actor.scope
    earlier = None if body.resume is None else await _resumed(session, serving, org_scope, body)
    if earlier is not None:
        keys.check_agent(actor, earlier.agent)
    if earlier is not None and earlier.waiting:
        return _back_in(serving, org_scope, body, earlier)
    named = body.agent or (None if earlier is None else earlier.agent)
    agent = named or fleet.client_named_agent(body.room_config)
    if agent is None:
        raise ValidationError(NO_AGENT_NAMED)
    keys.check_agent(actor, agent)
    if serving.registry.serving(org_scope, agent, None) is None:
        raise NotFound(NO_AGENT.format(slug=agent))
    the_fleet = await fleet.fleet_of_env(session, org_scope.env)
    await _room_for_one_more(serving, the_fleet, agent)
    await admit_call(session, serving, org_scope, agent)
    call = new_call_id()
    ttl = min(body.ttl_s or tokens.ONE_VISIT_TTL_S, LONGEST_VISIT_TTL_S)
    expires_at = time.time() + ttl
    scope = _visit_scope(body.scope)
    visitor = body.participant_identity or _caller_of(earlier) or f"web_{new_call_id()[5:17]}"
    carried = Dispatch(
        agent=agent,
        org=org_scope.org,
        env=org_scope.env,
        holder=org_scope.holder or None,
        scope=scope,
        caller=visitor,
        contact=body.contact or _contact_of(earlier),
        metadata=body.metadata,
        continues=None if earlier is None else earlier.call,
        tuning=_ask_test_values(body, actor),
    )
    token = tokens.room_token(
        serving.signer,
        call,
        scope,
        tokens.Visitor(expires_at=expires_at, identity=visitor, dispatch=fleet.room_dispatch(the_fleet, carried)),
    )
    await tokens.record_minted(session, call, org_scope, agent, scope, expires_at)
    return MintTokenResponse(
        server_url=serving.handles.settings.browser_livekit_url(org_scope.env),
        participant_token=token,
        call=call,
        log_token=tokens.log_token(serving.signer, call, body.log),
        resume_token=tokens.resume_token(serving.signer, call),
    )


# A test room's own voice and models are what the key that edits the pipeline may try, in the sandbox.
def _ask_test_values(body: MintTokenRequest, actor: Actor) -> dict[str, Any]:
    if not body.tuning:
        return {}
    if KeyScope.pipeline not in actor.scopes:
        raise Forbidden("a key that opens `pipeline` tries another voice or model in a test room")
    return settings.check_test_values(body.tuning, env=actor.env)


# The number is the key's own agent's in the key's env: a key issues codes for its agents.
async def issue_code(
    session: AsyncSession, serving: Serving, actor: Actor, body: IssueCodeRequest
) -> IssueCodeResponse:
    """Four digits for a caller to key, the number to call, and a token that asks after them."""
    keys.check_agent(actor, body.agent)
    routes = await channels.routes_of_org(session, actor.org, actor.env)
    number = next(
        (route.number for route in routes if route.agent == body.agent and route.channel is Channel.phone), None
    )
    if number is None:
        raise Conflict(f"agent {body.agent} answers at no phone number in {actor.env}: import one first")
    issued = await serving.codes.issue(session, actor.env, body.agent, body.ttl_s, body.log)
    # The token outlives the code a little, so the page is told it expired rather than refused.
    asks_until = issued.expires_at + A_PAGE_MAY_ASK_AFTER_S
    token = tokens.code_token(serving.signer, issued.code, body.agent, actor.env, asks_until)
    return IssueCodeResponse(code=issued.code, number=number, expires_at=issued.expires_at, code_token=token)


# A page holds no key: the code token its page was handed is the only credential.
async def code_status(
    session: AsyncSession, serving: Serving, visit: tokens.Visit, code: str, *, wait: bool
) -> CodeStatus:
    """How the code stands; with wait, held up to 25 s for a call to key it."""
    if visit.code != code or visit.agent is None or visit.env is None:
        raise Forbidden("this token reads another code")
    issued = await serving.codes.status_of(session, visit.env, visit.agent, code)
    if issued is None:
        raise NotFound(
            f"no code {code} is waiting for agent {visit.agent}: nobody issued it, it expired, or a call took it"
        )
    left = issued.expires_at - time.time()
    if wait and issued.claimed is None and left > 0:
        issued = await serving.codes.wait_for(session, issued, min(LONGEST_WAIT_S, left))
    if issued.claimed is not None:
        token = tokens.log_token(serving.signer, issued.claimed, issued.log)
        return CodeStatus(
            code=code, status="claimed", expires_at=issued.expires_at, call=issued.claimed, log_token=token
        )
    status = "expired" if time.time() >= issued.expires_at else "waiting"
    return CodeStatus(code=code, status=status, expires_at=issued.expires_at, call=None, log_token=None)


async def admit_call(session: AsyncSession, serving: Serving, scope: Scope, agent: str) -> billing.Ceiling | None:
    """Admit one more call of the org in its env, or write the refusal to the agent's log."""
    try:
        return await billing.admit_call(
            session,
            scope.org,
            scope.env,
            running=serving.live.running(scope.org, scope.env),
            at=serving.logs.store.clock(),
        )
    except QuotaExceeded as refused:
        await alerts.credits_refused(serving, scope, agent, refused)
        raise


# A gateway nobody's worker reported to refuses nobody.
async def _room_for_one_more(serving: Serving, the_fleet: str, agent: str) -> None:
    roster: fleet.Roster = serving.roster
    totals = roster.totals_of(the_fleet, time.time())
    if not totals.full:
        return
    full = FleetFull(channel=Channel.web, workers=totals.workers, active=totals.active)
    await serving.logs.agent(agent).append("fleet.full", full.dump())
    raise FleetIsFull(totals.active, totals.workers)


def _refuse_what_is_ours(body: MintTokenRequest) -> None:
    for field_name, sent in (
        ("room_name", body.room_name),
        ("participant_name", body.participant_name),
        ("participant_metadata", body.participant_metadata),
    ):
        if sent is not None:
            raise ValidationError(f"{field_name} is minted here and refused in the body: {OURS_TO_SET[field_name]}")
    if any(name.startswith(OUR_ATTRIBUTES) for name in body.participant_attributes):
        raise ValidationError(f"participant_attributes under {OUR_ATTRIBUTES} are minted here")


def _visit_scope(scope: str) -> tokens.RoomScope:
    for visit in tokens.MINTED_FOR_A_VISIT:
        if visit == scope:
            return visit
    raise ValidationError(
        f"scope is one of {sorted(tokens.MINTED_FOR_A_VISIT)}: observe and supervise take the API key instead"
    )


# The call is its org's and env's alone; a token of another's is refused as one nobody opened.
async def _resumed(session: AsyncSession, serving: Serving, org_scope: Scope, body: MintTokenRequest) -> Earlier:
    call = None if body.resume is None else tokens.resumed_call(serving.signer, body.resume)
    if call is None:
        raise Forbidden(NOT_A_RESUME)
    kept = await HeadRepository(session).head_of_call(call)
    opening = await openings.opening_of(session, call)
    if kept is None or kept.scope != org_scope or opening is None:
        raise NotFound(f"call {call} was not opened by this key's org and env: it cannot be resumed")
    if body.agent is not None and body.agent != kept.agent:
        raise ValidationError(f"call {call} is agent {kept.agent}'s, not {body.agent}'s: resume it with its own agent")
    server = serving.handles.servers[org_scope.env]
    waiting = not kept.sealed and call in await fleet.rooms_with_an_agent(server, [call])
    context = opening.context
    return Earlier(call, kept.agent, context.caller, context.contact, waiting)


# The agent is still in the room, waiting for the visitor: they sit back down as who they were,
# and the call goes on. No dispatch rides the token, so no second call can open from it.
def _back_in(serving: Serving, org_scope: Scope, body: MintTokenRequest, earlier: Earlier) -> MintTokenResponse:
    ttl = min(body.ttl_s or tokens.ONE_VISIT_TTL_S, LONGEST_VISIT_TTL_S)
    seated = tokens.Visitor(expires_at=time.time() + ttl, identity=earlier.caller)
    token = tokens.room_token(serving.signer, earlier.call, _visit_scope(body.scope), seated)
    return MintTokenResponse(
        server_url=serving.handles.settings.browser_livekit_url(org_scope.env),
        participant_token=token,
        call=earlier.call,
        log_token=tokens.log_token(serving.signer, earlier.call, body.log),
        resume_token=tokens.resume_token(serving.signer, earlier.call),
    )


def _caller_of(earlier: Earlier | None) -> str | None:
    return None if earlier is None else earlier.caller


def _contact_of(earlier: Earlier | None) -> str | None:
    return None if earlier is None or earlier.contact is None else earlier.contact.id
