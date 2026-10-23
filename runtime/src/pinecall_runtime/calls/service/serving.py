"""A call served here, as an endpoint reaches it: its socket, set up, first seen, known, claimed."""

import asyncio
import time
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from typing import Literal

from sqlalchemy.ext.asyncio import AsyncSession

from pinecall_runtime.accounts.service import mail, tokens
from pinecall_runtime.agents.declaration import AgentConfig
from pinecall_runtime.agents.service import prompts as agents_prompts
from pinecall_runtime.agents.service import registry as agents_registry
from pinecall_runtime.billing import service as billing
from pinecall_runtime.calls import private
from pinecall_runtime.calls.context import CallContext
from pinecall_runtime.calls.logs import Log, Logs
from pinecall_runtime.calls.repository.entries import EntryRepository
from pinecall_runtime.calls.repository.heads import CallHead, HeadRepository
from pinecall_runtime.calls.schemas import LookupRequest
from pinecall_runtime.calls.service import openings
from pinecall_runtime.calls.service.codes import Codes
from pinecall_runtime.calls.service.counters import VendorCounters
from pinecall_runtime.calls.service.live import Live, Served
from pinecall_runtime.calls.service.tool_calls import ToolCalls
from pinecall_runtime.enums import Direction, KeyScope, Opener
from pinecall_runtime.exceptions import Conflict, Forbidden, NotFound, ValidationError
from pinecall_runtime.fleet import service as fleet
from pinecall_runtime.kit.auth import Actor, Scope
from pinecall_runtime.kit.handles import Handles
from pinecall_runtime.kit.text import JsonObject
from pinecall_runtime.knowledge import service as knowledge
from pinecall_runtime.knowledge.service import embedder as knowledge_embedder
from pinecall_runtime.providers import service as providers
from pinecall_runtime.wire.base import Entry
from pinecall_runtime.wire.events import EVENTS, GATEWAY_WRITES, CallClaimed
from pinecall_runtime.wire.parts import ToolResult

NOT_OPEN = "this gateway is not writing call {call!r}: open it with POST /v1/calls first"
SEALED = "call {call!r} is over: nothing more can be written to it"
NO_SUCH_CALL = "no call {call} in this key's org and env"
ERROR = "error"
SWITCHED = "vendor.switched"


# What serves a call on this gateway: one of each, built by the lifespan.
@dataclass(frozen=True)
class Serving:
    """The process's handles, the logs, the calls live in it, and what every call reaches."""

    handles: Handles
    logs: Logs
    # Every email the gateway sends: an alert's, among them.
    outbox: mail.Outbox
    live: Live
    registry: agents_registry.AgentRegistry
    signer: tokens.Signer
    codes: Codes
    # None when the box embeds nothing: every lookup finds nothing and no hang-up remembers.
    embedder: knowledge_embedder.Embedder | None
    prompts: agents_prompts.PromptCache
    counters: VendorCounters
    # The fleet as this gateway hears it, and the dispatcher that sends a call into a room.
    roster: fleet.Roster
    offering: fleet.Offering

    @property
    def now(self) -> datetime:
        """This moment by the store's clock, the one every entry of a call is stamped with."""
        return datetime.fromtimestamp(self.logs.store.clock(), UTC)


# A call opened with a key goes to that key's scope; one that rang, to its phone owner, or the line.
def serving_agent(
    registry: agents_registry.AgentRegistry,
    scope: Scope,
    agent: str,
    app: agents_registry.SocketId | None,
    context: CallContext,
) -> agents_registry.Registration | None:
    """The socket a new call of the agent reaches."""
    if app is None and context.route.channel.has_a_number:
        return registry.taking_a_ring(agents_registry.orgs_own(scope), agent, context.caller)
    return registry.serving(scope, agent, app)


def serve_call(
    serving: Serving, owner: agents_registry.SocketId | None, context: CallContext, config: AgentConfig, scope: Scope
) -> Served:
    """Serve the call to its socket, or park it for the next one; before its first entry."""
    log = serving.logs.writing(context.call, config.slug)
    log.privacy = private.Privacy(serving.handles.vault, config)
    sessions = serving.handles.sessions

    async def answered_before(call_id: str) -> ToolResult | None:
        async with sessions() as session_:
            answered = await EntryRepository(session_).tool_answered(context.call, call_id)
        # What the model reads is what the app answered, not what the log keeps of it.
        return None if answered is None else ToolResult.model_validate((await log.opened(answered)).data)

    async def called_before(call_id: str) -> Entry | None:
        async with sessions() as session_:
            return await EntryRepository(session_).tool_called(context.call, call_id)

    served = Served(
        agent=config.slug,
        scope=scope,
        app=owner,
        log=log,
        commands=asyncio.Queue(),
        context=context,
        config=config,
        tools=ToolCalls(config, log, answered_before, called_before),
    )
    serving.live.serve(served)
    return serving.live.calls[context.call]


# Committed on its own, before the call is served: `Live.serve` tells the gateway holding the
# agent's socket of the call at once, and that gateway reads the opening to take it (`known_here`).
# A row still in the opener's transaction is not there yet, the word is dropped, and the call
# never reaches its app: every tool it calls waits out its deadline.
async def kept_before_served(serving: Serving, org: str, context: CallContext, config: AgentConfig) -> None:
    """The call's opening and its prompt, written and committed before any gateway is told of it."""
    async with serving.handles.sessions.begin() as session_:
        await openings.keep_opening(session_, org, context, config)
        await serving.prompts.keep(session_, org, config.knowledge or "")


# Parked and not counted: the socket holding its agent and the quota are its opener's.
def first_seen(serving: Serving, context: CallContext, config: AgentConfig, kept: CallHead, now: float) -> Served:
    """Serve a call another gateway opened, from what was kept when it opened."""
    serving.live.let_idle_go(now)
    served = serve_call(serving, None, context, config, kept.scope or Scope(context.route.org, context.env))
    served = replace(served, opened_here=False, opened_by=kept.opened_by)
    serving.live.calls[served.call] = served
    serving.live.seen[served.call] = now
    return served


async def write_arrival(log: Log, context: CallContext, agent: str) -> None:
    """call.ringing for an inbound call; an outbound one has its call.dialing already."""
    if context.direction is Direction.outbound:
        return
    kind, data = openings.arrival_entry(context, context.route.number or agent)
    await log.append(kind, data)


# The quotas are read per lookup, so a plan changed mid-call applies from the next turn.
async def look_up(session_: AsyncSession, serving: Serving, served: Served, request: LookupRequest) -> JsonObject:
    """Recall or search for a call served here, written on its log, answered as the model reads."""
    quotas = await billing.get_quotas(session_, served.scope.org, served.scope.env)
    call = knowledge.LookupCall(
        scope=served.scope,
        call=served.call,
        channel=served.context.channel,
        contact=served.context.remembered_as,
        config=served.config,
        log=served.log,
        now=serving.now,
    )
    asked = knowledge.LookupRequest(tool=request.tool, input=request.input, speech_id=request.speech_id)
    return await knowledge.lookup(session_, serving.embedder, call, asked, quotas=quotas)


async def claim_code(
    session_: AsyncSession, codes: Codes, served: Served, code: str, *, via: Literal["keypad", "agent"]
) -> bool:
    """Tie the call to the page showing the code; False when no page waits on it."""
    issued = await codes.claim(session_, served.scope.env, served.agent, code, served.call)
    if issued is None:
        return False
    await served.log.append("call.claimed", CallClaimed(code=code, via=via).dump())
    return True


# None for a call nobody claimed, one sealed, or one opened by a release that kept no opening.
async def known_here(session_: AsyncSession, serving: Serving, call: str) -> Served | None:
    """The call as this gateway serves it, first seen here from its opening when need be."""
    served = serving.live.calls.get(call)
    if served is not None:
        return served
    kept = await HeadRepository(session_).head_of_call(call)
    if kept is None or kept.scope is None or kept.sealed:
        return None
    opening = await openings.opening_of(session_, call)
    if opening is None:
        return None
    return first_seen(serving, opening.context, opening.config, kept, time.monotonic())


# An id grants nothing: another org's or env's call is the same 404 as a call nobody opened.
# The fleet's key serves every org of its env; a tenant's worker its own org alone.
# A call this gateway serves, or one another gateway opened, served here from what was kept when
# it opened: one read, the first time an endpoint here asks. A call opened by a release that kept
# nothing is the 404 a worker answers by saying the call again (`/reopened`).
# A worker's endpoint is the opener's (`openers`); the lookup is any key's of the call's org and env.
async def get_served(
    session_: AsyncSession, serving: Serving, actor: Actor, call: str, *, openers: bool = True
) -> Served:
    """The call as this gateway serves it, first seen here if need be; a refusal names why."""
    now = time.monotonic()
    served = serving.live.calls.get(call)
    if served is not None:
        _check_yours(actor, served.scope, served.opened_by if openers else None, call)
        serving.live.in_use(call, now)
        return served
    kept = await HeadRepository(session_).head_of_call(call)
    if kept is None or kept.scope is None:
        raise NotFound(NOT_OPEN.format(call=call))
    _check_yours(actor, kept.scope, kept.opened_by if openers else None, call)
    if kept.sealed:
        raise Conflict(SEALED.format(call=call))
    opening = await openings.opening_of(session_, call)
    if opening is None:
        raise NotFound(NOT_OPEN.format(call=call))
    return first_seen(serving, opening.context, opening.config, kept, now)


def check_kind(kind: str) -> None:
    """Refuse a type the protocol lacks, or one the gateway alone writes on a log."""
    if kind not in EVENTS:
        raise ValidationError(f"no event is called {kind!r}: the log takes the protocol's own words")
    if kind in GATEWAY_WRITES:
        raise Forbidden(f"{kind!r} is written by the gateway itself, never sent to it")


# The gateway itself reads these two back to end a call and to hand it on, so a worker's that does
# not parse is refused where it is sent, naming the field: a call whose start the seal cannot read
# could never be sealed (2026-10-23: a call.started with no `caller` was taken, and its seal
# answered 500 for ever, the call holding its seat).
LIFECYCLE = ("call.started", "call.ended")


def check_entry(kind: str, data: JsonObject) -> None:
    """Refuse an entry the log does not take: its type, or the shape of a lifecycle entry."""
    check_kind(kind)
    if kind in LIFECYCLE:
        EVENTS[kind].parse(data, kind)


# What /metrics reads: the append's time at the endpoint, and each vendor's failures as they
# come in. A vendor fails a call when an error names its plugin, or when a stage switches away.
def count_append(counters: VendorCounters, seconds: float, entries: list[Entry]) -> None:
    """Count an append's time and entries, and what they say of vendors, for /metrics."""
    counters.appended_in(seconds, len(entries))
    at = time.monotonic()
    for entry in entries:
        vendor = ""
        if entry.type == ERROR:
            code, message = entry.data.get("code"), entry.data.get("message")
            vendor = providers.vendor_named_in(message if isinstance(message, str) else "")
            counters.failed(code if isinstance(code, str) else "", vendor)
        elif entry.type == SWITCHED and entry.data.get("available") is False:
            named = entry.data.get("vendor")
            vendor = named if isinstance(named, str) else ""
        if vendor and entry.call is not None:
            counters.failed_on(vendor, entry.call, at)


def is_the_fleet(actor: Actor) -> bool:
    """Whether the actor is an env's fleet, which serves every org of its env."""
    return KeyScope.fleet in actor.scopes


# A call the fleet opened is the fleet's to write; a written call runs here and no worker
# endpoint serves it; one an org's own worker opened is that org's. One opened before the head
# said who is served as before.
def _check_yours(actor: Actor, scope: Scope, opened_by: Opener | None, call: str) -> None:
    fleet = is_the_fleet(actor)
    if scope.env != actor.env or (not fleet and scope.org != actor.org):
        raise NotFound(NOT_OPEN.format(call=call))
    if opened_by is Opener.gateway or (opened_by is Opener.fleet and not fleet):
        raise NotFound(NOT_OPEN.format(call=call))
