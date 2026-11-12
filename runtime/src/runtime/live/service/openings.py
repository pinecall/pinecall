"""A call opened and a call served again: admitted, claimed, its opening kept, then served; the worker's open."""

import logging
import time
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Literal

from sqlalchemy.ext.asyncio import AsyncSession

from runtime.accounts import service as accounts
from runtime.actor import Actor, Scope
from runtime.agents import service as agents
from runtime.agents.settings import Versions
from runtime.billing import service as billing
from runtime.calls import service as calls
from runtime.calls.context import CallContext
from runtime.calls.models import Opener
from runtime.compliance import service as compliance
from runtime.enums import Direction
from runtime.exceptions import Conflict, Forbidden, NotFound, QuotaExceeded, ValidationError
from runtime.kit.crypto import Vault
from runtime.live.holders import Holders, NobodyTakes, NotThatApp, Registration, orgs_own
from runtime.live.parts import LiveParts
from runtime.live.repository import TokenRepository
from runtime.live.served import Opening, Served
from runtime.live.service import handoff
from runtime.live.sockets import SocketId
from runtime.live.tool_calls import ToolCalls
from runtime.providers import service as providers
from runtime.scoping import box_wide
from runtime.telephony import service as telephony
from runtime.wire.base import Entry
from runtime.wire.events import CallRinging, ErrorEvent
from runtime.wire.parts import Route, ToolResult

logger = logging.getLogger(__name__)

SPENT = "token_spent"
ALREADY_SPENT = "call {call} was opened by its token already: a token opens one call, once"

# What spending a call's token answers: spent now, never minted (a phone, a dial, a run), minted for
# another org, env or agent, or spent before.
type Spending = Literal["spent", "never_minted", "minted_elsewhere", "already_spent"]


@dataclass(frozen=True, slots=True)
class Arrival:
    """What a worker opens a call with, and says again to a gateway that forgot it."""

    agent: str
    context: CallContext
    # The app socket that must serve it (a spoken golden run); else the one the call reaches.
    app: SocketId | None = None
    # The Twilio account an inbound leg says it came from; None from any other carrier.
    carrier_account: str | None = None
    # The test room's own voice and models the worker runs this call on.
    test_values: Mapping[str, Any] | None = None


@dataclass(frozen=True, slots=True)
class Opened:
    """What a worker is answered for the call it opened: what its minutes leave it, and what it says first."""

    ceiling: billing.Ceiling | None
    # An outbound call's AI disclosure, and the notice a recorded call says; None for none.
    disclosure: str | None
    recording_notice: str | None
    # The turns of the call this one continues, oldest first; empty for a call of its own.
    history: list[Entry]


# ── the two verbs ──


# A refusal is said on the agent's log in a transaction of its own: the request's is rolled back with
# the refusal, and an alert it took with it was never kept (`alerts.Alerting.credits_exhausted`).
async def admit(session: AsyncSession, live: LiveParts, scope: Scope, agent: str) -> billing.Ceiling | None:
    """Admit one more call of the org in its env, or write the refusal to the agent's log."""
    try:
        return await billing.admit_call(
            session, scope.org, scope.env, running=live.calls.holding(scope.org, scope.env), at=live.store.clock()
        )
    except QuotaExceeded as refused:
        async with live.sessions.begin() as own:
            await live.alerting.credits_exhausted(own, scope, agent, refused)
        raise


# The one order a new call is served in; whoever opens one adds its guards before and its own after
# (the worker its first entry, a written call its session). Until 2026-11 five functions each wrote
# the steps again, and who opened the call was said after it was served.
#
# The claim, the opening and the prompt are committed on their own, before the call is served: serving
# it tells the gateway holding the agent's socket of the call at once, and that gateway reads the
# opening to take it. A row still in the opener's transaction is not there yet, the word is dropped,
# and the call never reaches its app: every tool it calls waits out its deadline.
async def open_served(live: LiveParts, opening: Opening, versions: Versions) -> Served:
    """Serve a new call: its head claimed and its opening kept, then served here and its commands heard."""
    context, declaration, scope = opening.context, opening.declaration, opening.scope
    async with live.sessions.begin() as own:
        claim = calls.Claim(scope, versions, opened_by=opening.opened_by)
        await calls.claim_call(own, context.call, declaration.slug, claim)
        await calls.keep_opening(own, scope.org, context, declaration)
        await live.prompts.keep(own, scope.org, declaration.knowledge or "")
    served = serve(live, opening, opened_here=True)
    await live.calls.wait_until_heard(context.call)
    return served


# A call that exists already (another gateway opened it, this one restarted, a chat was taken up) runs
# on what was kept when it opened: its context and its declaration, from the one row. Until 2026-11
# the context came from three places and the declaration was resolved anew on a restart, so a call
# changed its settings because a gateway did (calls-service-6): the opening kept wins.
#
# A call that kept none is resolved as a call opening now would be, from what is `known` of it: what
# its worker says again, or what its own call.started said. Such calls exist in the database this
# release runs on: the ones opened before openings were kept, and one whose gateway died between its
# claim and its opening. What is resolved is kept, committed, before the call is served, as a new
# call's is: the gateway holding its agent's socket reads it to take the call. With no opening and
# nothing known, nothing is served: the worker is answered the 404 it answers by saying the call again.
#
# `adopt` is for the gateway that takes the call over (it counts it against its org and hands it on);
# without it the call is a copy: parked, not counted, and let go once nobody asks for it.
async def serve_again(
    session: AsyncSession,
    live: LiveParts,
    call: str,
    kept: calls.CallHead,
    *,
    adopt: bool,
    known: CallContext | None = None,
    test_values: Mapping[str, Any] | None = None,
) -> Served | None:
    """Serve a call from the opening it kept, else resolved anew from what is known of it; None with neither."""
    opening = await calls.opening_of(session, call)
    if opening is not None:
        scope = kept.scope or Scope(opening.context.route.org, opening.context.env)
        again = Opening(opening.context, opening.declaration, scope, kept.opened_by)
    elif known is not None and kept.scope is not None:
        resolved = await _resolve(session, kept.scope, kept.agent, call, test_values)
        async with live.sessions.begin() as own:
            await calls.keep_opening(own, kept.scope.org, known, resolved.declaration)
            await live.prompts.keep(own, kept.scope.org, resolved.declaration.knowledge or "")
        again = Opening(known, resolved.declaration, kept.scope, kept.opened_by)
    else:
        return None
    if adopt:
        served = serve(live, again, opened_here=True)
        await live.calls.wait_until_heard(call)
        return served
    now = time.monotonic()
    live.calls.let_idle_go(now)
    return serve(live, again, opened_here=False, seen_at=now)


def serve(live: LiveParts, opening: Opening, *, opened_here: bool, seen_at: float | None = None) -> Served:
    """The call served on this gateway, to its socket or parked for the next one; before its first entry."""
    call = opening.context.call
    # A call served already stays as it is: its log goes on masking by what it learned.
    already = live.calls.find(call)
    if already is not None:
        return already
    log = live.logs.writing(call, opening.declaration.slug)
    log.mask_by(live.vault, opening.declaration)

    async def find_answer(call_id: str) -> ToolResult | None:
        async with live.sessions() as session:
            answered = await calls.find_tool_entry(session, call, "tool.result", call_id)
        # What the model reads is what the app answered, not what the log keeps of it.
        return None if answered is None else ToolResult.model_validate((await log.privacy.open(answered)).data)

    async def find_call(call_id: str) -> Entry | None:
        async with live.sessions() as session:
            return await calls.find_tool_entry(session, call, "tool.call", call_id)

    tools = ToolCalls(opening.declaration, log, find_answer, find_call)
    return live.calls.serve(Served(opening, log, tools, opened_here=opened_here), seen_at=seen_at)


# A call opened with a key goes to that key's scope; one that rang, to its phone owner, or the line.
def find_serving_agent(
    holders: Holders, scope: Scope, agent: str, app: SocketId | None, context: CallContext
) -> Registration | None:
    """The socket a new call of the agent reaches."""
    if app is None and context.route.channel.has_a_number:
        return holders.find_ring_taker(orgs_own(scope), agent, context.caller)
    return holders.find_serving(scope, agent, app)


# ── a call an endpoint asks for ──


# None for a call nobody claimed, one sealed, or one that kept no opening.
async def find_served(session: AsyncSession, live: LiveParts, call: str) -> Served | None:
    """The call as this gateway serves it, served again here from its opening when need be."""
    served = live.calls.find(call)
    if served is not None:
        return served
    kept = await calls.find_head(session, call)
    if kept is None or kept.scope is None or kept.sealed:
        return None
    return await serve_again(session, live, call, kept, adopt=False)


# An id grants nothing: another org's or env's call is the same 404 as a call nobody opened.
# The fleet's key serves every org of its env; a tenant's worker its own org alone.
# A call this gateway serves, or one another gateway opened, served here from what was kept when
# it opened: one read, the first time an endpoint here asks. A call that kept nothing is the 404 a
# worker answers by saying the call again (`/reopened`).
# A worker's endpoint is the opener's (`openers`); the lookup is any key's of the call's org and env.
async def get_served(
    session: AsyncSession, live: LiveParts, actor: Actor, call: str, *, openers: bool = True
) -> Served:
    """The call as this gateway serves it, served again here if need be; a refusal names why."""
    served = live.calls.find(call)
    if served is not None:
        _check_yours(actor, served.scope, served.opened_by if openers else None, call)
        live.calls.touch(call, time.monotonic())
        return served
    kept = await calls.find_head(session, call)
    if kept is None or kept.scope is None:
        raise NotFound(f"this gateway is not writing call {call!r}: open it with POST /v1/calls first")
    _check_yours(actor, kept.scope, kept.opened_by if openers else None, call)
    if kept.sealed:
        raise Conflict(f"call {call!r} is over: nothing more can be written to it")
    served = await serve_again(session, live, call, kept, adopt=False)
    if served is None:
        raise NotFound(f"this gateway is not writing call {call!r}: open it with POST /v1/calls first")
    return served


# ── the worker's ──


# The log opens before the media, so a console sees the call ring; call.started is the worker's.
async def open_call(session: AsyncSession, live: LiveParts, actor: Actor, arrival: Arrival) -> Opened:
    """Open a call's log, serve it to its agent's socket, say its minutes and its first words."""
    context = arrival.context
    accounts.check_agent(actor, arrival.agent)
    scope = scope_of_call(actor, context)
    if context.direction is Direction.inbound and context.route.number is not None:
        await _check_arrival(session, live.vault, scope, context.route.number, arrival.carrier_account)
    await _check_unclaimed_or_in(session, context.call, scope)
    await _spend_token(session, live, context, scope, arrival.agent)
    ceiling = await admit(session, live, scope, arrival.agent)
    registration = find_serving_agent(live.holders, scope, arrival.agent, arrival.app, context)
    _check_served(live.holders, scope, arrival, registration)
    resolved = await _resolve(session, scope, arrival.agent, context.call, arrival.test_values)
    # Asked again by a worker whose gateway died with the answer: the same call, one ringing.
    again = await calls.opening_of(session, context.call) is not None
    # A worker opened the room's call: nothing is left to offer it to another.
    await live.offering.forget(context.call)
    opener = Opener.fleet if actor.is_fleet else Opener.app
    owner = None if registration is None else registration.owner
    served = await open_served(live, Opening(context, resolved.declaration, scope, opener, owner), resolved.versions)
    if not again:
        await write_arrival(served)
    policy = await compliance.policy_of(session, scope.org)
    org = await accounts.find_org(session, scope.org)
    name = scope.org if org is None else org.name
    language = resolved.declaration.language
    return Opened(
        ceiling=ceiling,
        # The worker says the disclosure before the greeting, and the notice only where it records.
        disclosure=policy.disclosure_for(name, language) if context.direction is Direction.outbound else None,
        recording_notice=policy.notice_in(language),
        history=await _list_carried(session, live.vault, scope, arrival),
    )


# A gateway that restarted forgot the call: served again from what it kept, no quota, no token, no
# second call.ringing; the socket holding its agent hears call.attached. A call that kept no opening
# is resolved anew from the worker's word (`serve_again`).
async def reopen_call(session: AsyncSession, live: LiveParts, actor: Actor, call: str, arrival: Arrival) -> None:
    """Serve again a call the gateway forgot."""
    if call != arrival.context.call:
        raise ValidationError(f"the context is call {arrival.context.call!r}, not {call!r}")
    if live.calls.find(call) is not None:
        return
    scope = scope_of_call(actor, arrival.context)
    kept = await calls.find_head(session, call)
    if kept is None or kept.scope is None:
        raise NotFound(f"this gateway is not writing call {call!r}: open it with POST /v1/calls first")
    if kept.scope != scope:
        raise NotFound(f"no call {call} in this key's org and env")
    if kept.sealed:
        raise Conflict(f"call {call!r} is over: nothing more can be written to it")
    await serve_again(session, live, call, kept, adopt=True, known=arrival.context, test_values=arrival.test_values)
    registration = live.holders.find_serving(scope, arrival.agent)
    if registration is not None:
        await handoff.attach(live.calls, call, registration.owner)


# The caller is always the far end. An outbound call has its call.dialing already, written when it
# was placed (`dialing.place_call`).
async def write_arrival(served: Served) -> None:
    """call.ringing for an inbound call."""
    context = served.context
    if context.direction is Direction.outbound:
        return
    ringing = CallRinging.parse(
        {
            "channel": context.channel.value,
            "from": context.caller,
            "to": context.route.number or served.agent,
            "run": context.run,
            "caller": None,
            "route": Route(channel=context.route.channel, number=context.route.number).dump(),
        },
        "call.ringing",
    )
    await served.log.append("call.ringing", ringing.dump())


# A tenant's worker opens its own org's calls in its own env; the fleet's opens any org's in
# its env, in the scope the dispatch named.
def scope_of_call(actor: Actor, context: CallContext) -> Scope:
    """The scope the call is opened in, as this key may open it."""
    named = Scope(context.route.org, context.env, context.holder or "")
    if actor.is_fleet:
        # A fleet serves one env: a unit holding the other env's key is refused here too.
        if named.env is not actor.env:
            raise Forbidden(f"this key opens {actor.env}, and that call's route answers in {named.env}")
        return named
    if context.route.org != actor.org:
        raise NotFound(f"no call {context.call} in this key's org and env")
    if context.env is not actor.env:
        raise Forbidden(f"this key opens {actor.env}, and that call's route answers in {context.env}")
    return actor.scope


# `tokens` names its org with no key to it: retention calls this when an org is erased.
async def delete_tokens(session: AsyncSession, org: str) -> int:
    """Forget every room token minted for the org; how many went."""
    with box_wide():
        return await TokenRepository(session).delete_of_org(org)


# ── private ──


# A call the fleet opened is the fleet's to write; a written call runs here and no worker
# endpoint serves it; one an org's own worker opened is that org's. One opened before the head
# said who is served as before.
def _check_yours(actor: Actor, scope: Scope, opened_by: Opener | None, call: str) -> None:
    if scope.env != actor.env or (not actor.is_fleet and scope.org != actor.org):
        raise NotFound(f"this gateway is not writing call {call!r}: open it with POST /v1/calls first")
    if opened_by is Opener.gateway or (opened_by is Opener.fleet and not actor.is_fleet):
        raise NotFound(f"this gateway is not writing call {call!r}: open it with POST /v1/calls first")


# The carrier, the fence and the env rule worked, whatever is refused here. A number the org
# hooked rings nobody until the operator approves it is the org's; a call Twilio sent from an
# account the number does not live in is somebody else's Twilio pointed at it.
async def _check_arrival(session: AsyncSession, vault: Vault, scope: Scope, number: str, came_from: str | None) -> None:
    await telephony.note_call(session, scope.org, number)
    try:
        route = await telephony.get_number(session, scope.org, number)
    except NotFound:
        route = None
    if route is not None and not route.approved:
        raise Forbidden(
            f"{number} was hooked by the org and waits for the box's operator to approve it: no call to it "
            "opens until then"
        )
    if came_from is None:
        return
    expected = await telephony.twilio_account_of(session, vault, scope.org, number)
    if expected is not None and expected != came_from:
        raise Forbidden(f"{number} lives in another Twilio account than the one this call came from: refused")


# A call a dial placed already has its head: the worker opens it in the scope the head keeps, or
# not at all, whatever its key; the first claim of a head stands, so this is the one check.
async def _check_unclaimed_or_in(session: AsyncSession, call: str, scope: Scope) -> None:
    kept = await calls.find_head(session, call)
    if kept is not None and kept.scope is not None and kept.scope != scope:
        raise NotFound(f"no call {call} in this key's org and env")


# A web call opens by the token its room was minted with: once, and only in the org, the env
# and for the agent it was minted for. Asked of the ledger by the call's id, whatever the worker
# says: a call no token was minted for (a phone, a dial, a run) is not a token's to refuse.
async def _spend_token(session: AsyncSession, live: LiveParts, context: CallContext, scope: Scope, agent: str) -> None:
    spending = await spend_token(session, context.call, scope, agent)
    if spending in {"spent", "never_minted"}:
        return
    if spending == "minted_elsewhere":
        logger.warning(
            "call %s was opened in org %s, %s, agent %s: its token was minted for another",
            context.call,
            scope.org,
            scope.env,
            agent,
        )
        raise NotFound(f"no call {context.call} in this key's org and env")
    sentence = ALREADY_SPENT.format(call=context.call)
    refused = ErrorEvent(code=SPENT, message=sentence, recoverable=True)
    await live.logs.agent(agent).append("error", refused.dump())
    raise Conflict(sentence)


async def spend_token(session: AsyncSession, call: str, scope: Scope, agent: str) -> Spending:
    """Spend the call's token in the scope the worker names, once; otherwise say why not."""
    tokens = TokenRepository(session)
    if await tokens.spend(call, scope.org, scope.env, agent):
        return "spent"
    row = await tokens.find(call)
    if row is None:
        return "never_minted"
    return "minted_elsewhere" if row.spent_at is None else "already_spent"


def _check_served(holders: Holders, scope: Scope, arrival: Arrival, registration: Registration | None) -> None:
    if arrival.app is not None and registration is None:
        raise NotThatApp(arrival.app, arrival.agent)
    # Held by consoles alone: refused before the greeting, rather than a call with no app.
    if registration is None and holders.find_holder(scope, arrival.agent) is not None:
        raise NobodyTakes(arrival.agent)


# What the agent's class declares is read from its row, the scope's own else the org's, whoever
# holds it now: a call that arrives before agent.configure runs on what the agent declared last.
# The call's id picks its version where the scope stands on a canary, the same on a reopen.
async def _resolve(
    session: AsyncSession, scope: Scope, slug: str, call: str, test_values: Mapping[str, Any] | None
) -> agents.Resolved:
    agent = await agents.agent_of(session, scope, slug)
    catalog = await providers.get_catalog(session)
    test = agents.check_test_values(test_values, env=scope.env)
    return await agents.resolve_for_call(session, agent.whole, scope, catalog, agents.Picked(call=call), test)


# The call carried on must be the same org's, env's and agent's, whatever the worker says.
async def _list_carried(session: AsyncSession, vault: Vault, scope: Scope, arrival: Arrival) -> list[Entry]:
    earlier = arrival.context.continues
    if earlier is None:
        return []
    kept = await calls.find_head(session, earlier)
    if kept is None or kept.scope != scope or kept.agent != arrival.agent:
        raise NotFound(f"call {arrival.context.call} carries on {earlier}, which is not its org's and agent's call")
    return await calls.list_carried(session, vault, earlier)
