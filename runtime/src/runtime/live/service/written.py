"""A written call, run by the gateway itself: opened on the socket that holds its agent, taken up again, heard."""

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, replace
from datetime import UTC, date, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from runtime.actor import Scope
from runtime.agents import service as agents
from runtime.agents.declaration import Declaration
from runtime.agents.settings import Versions
from runtime.billing import service as billing
from runtime.calls import service as calls
from runtime.calls.context import CallContext, Contact, Route
from runtime.calls.models import Opener
from runtime.enums import Channel, Direction
from runtime.exceptions import Conflict, QuotaExceeded, ValidationError
from runtime.kit.text import JsonObject
from runtime.kit.time import today_in
from runtime.live.holders import Registration
from runtime.live.parts import LiveParts
from runtime.live.served import Opening, Served
from runtime.live.service import handoff, lookups, openings, seal
from runtime.live.service.ending import Sealing
from runtime.providers import service as providers
from runtime.providers.stage import Running
from runtime.session import service as session
from runtime.wire.base import BatchedEntry, Entry
from runtime.wire.events import TERMINAL_EVENT, CallStarted, MemoryOps
from runtime.wire.metrics import LLMModelUsage, ModelUsage
from runtime.wire.parts import MemoryFact, MemoryOp, PlatformTool, ToolResult

# A written call's session runs on one gateway, which says so: another takes it up only once
# that gateway fell silent.
RUNS_ELSEWHERE = "call {call} runs on another gateway: it is taken up there"
# Where a fact a golden's recall answers is said to come from.
A_GOLDEN = "golden"
RECALL: PlatformTool = "recall"


@dataclass(frozen=True, slots=True)
class WrittenSetup:
    """What a written call runs on: its declaration as resolved, its versions, the model, a golden's facts."""

    declaration: Declaration
    versions: Versions
    model: Running
    # A golden's facts, which recall answers instead of the contact's memory; None on a real call.
    recalled: tuple[str, ...] | None = None


# What a session reaches outside itself when the gateway hosts it (`session.Platform`): the call's own
# log, the app's tools through it, the lookups, and the one end of a call. A class that holds the call
# as it is served now: until 2026-11 it was five closures over a copy of it, and the seal read the
# socket the call had when it opened.
class GatewayPlatform:
    """A written call's platform: its log, its tools, its lookups and its seal, on the gateway that runs it."""

    def __init__(self, live: LiveParts, served: Served, recalled: tuple[str, ...] | None) -> None:
        self._live = live
        self._served = served
        self._recalled = recalled

    async def append_many(self, entries: list[BatchedEntry], *, after: int) -> list[Entry]:
        """The entries on the call's log, numbered, after the ones it already took from this writer."""
        return await self._served.log.append_many(entries, after=after)

    async def run_tool(self, use: session.ToolUse, speech: str | None) -> ToolResult:
        """One of the app's tools run in the app's process, and what came back."""
        return await self._served.tools.run(use, speech)

    # A golden's recall reads the golden's facts and nothing else; its search is the real index, since
    # that is what the golden is asking about. The recall is written as a real one is, so the app
    # learns the facts.
    async def look_up(self, tool: PlatformTool, arguments: JsonObject, speech: str | None) -> JsonObject:
        """A recall or a search, written on the call's log and answered as the model reads it."""
        if self._recalled is None or tool != RECALL:
            return (await lookups.look_up(self._live, self._served, tool, arguments, speech)).output
        facts = [MemoryFact(text=fact, source=A_GOLDEN) for fact in self._recalled]
        query = arguments.get("query")
        op = MemoryOp(op="recall", query=str(query) if query else None, facts=facts, took_ms=0.0)
        await self._served.log.append("memory.ops", MemoryOps(ops=[op], speech_id=speech).dump())
        return {"facts": [{"text": fact, "source": A_GOLDEN} for fact in self._recalled]}

    async def seal(self, usage: list[ModelUsage], outcome: str) -> None:
        """The call is over: what its models used and the last thing it said."""
        await seal.seal_call(self._live, self._served, Sealing(usage=tuple(usage), outcome=outcome))

    async def release_seal(self) -> None:
        """The app's end hook ran: the seal that waits for it may go on."""
        self._served.hooked.set()


# A Studio agent is held once, by the org, and a person's written call reaches that socket by falling
# through to it. The socket stays the org's; the call is the person's, resolved at their level and
# claimed in their scope, as their voice call is. A scope names a holder only for a person, in the sandbox.
def registration_for(registration: Registration, scope: Scope) -> Registration:
    """The registration a written call opened in the scope runs on; a class's stays as it is held."""
    if scope.holder and agents.kind_of(registration.sdk) == "studio":
        return replace(registration, scope=scope)
    return registration


# ── opened, and taken up again ──


async def open_written(
    session_: AsyncSession,
    live: LiveParts,
    registration: Registration,
    context: CallContext,
    *,
    test: Mapping[str, Any] | None = None,
) -> session.Session:
    """A new written call on the socket that holds the agent, admitted and unstarted.

    `test` is a test room's own voice and models, checked at the endpoint, over the settings for this call alone.
    """
    scope = registration.scope
    agent = await agents.agent_of(session_, scope, registration.slug)
    catalog = await providers.get_catalog(session_)
    picked = agents.Picked(call=context.call)
    resolved = await agents.resolve_for_call(session_, agent.whole, scope, catalog, picked, test)
    keys = await providers.keys_of(session_, live.vault, scope)
    model = providers.thinking_of(resolved.declaration, catalog, keys)
    setup = WrittenSetup(resolved.declaration, resolved.versions, model)
    return await open_written_as(session_, live, registration, context, setup)


# Admission before the log is claimed: a refused call leaves nothing behind. Its opening is kept as
# a phone call's is: the gateway holding the app's socket serves it from it.
async def open_written_as(
    session_: AsyncSession, live: LiveParts, registration: Registration, context: CallContext, setup: WrittenSetup
) -> session.Session:
    """A new written call on this setup, admitted and unstarted."""
    scope = registration.scope
    await openings.admit(session_, live, scope, registration.slug)
    opening = Opening(context, setup.declaration, scope, Opener.gateway, registration.owner)
    served = await openings.open_served(live, opening, setup.versions)
    return start_session(live, served, setup.model, setup.recalled)


# A gateway that restarted forgot the call, not the caller: no admission, no second greeting. It runs
# on the declaration it opened on, with the model its org's keys give it now; one that kept no opening
# (it opened before openings were kept) is resolved anew, on what its call.started said of it.
async def resume_written(
    session_: AsyncSession, live: LiveParts, registration: Registration, call: str
) -> session.Session | None:
    """A written call taken up again from its log; None for one that is over or not this agent's."""
    kept = await calls.find_head(session_, call)
    if kept is None or kept.sealed or kept.scope is None or kept.agent != registration.slug:
        return None
    if live.owners.runs_elsewhere(call):
        raise Conflict(RUNS_ELSEWHERE.format(call=call))
    if kept.scope.org != registration.scope.org:
        return None
    # The model reads the tools' arguments as they were sent: the private ones opened.
    entries = await calls.read_whole(session_, live.vault, call)
    if not entries or any(entry.type == TERMINAL_EVENT for entry in entries):
        return None
    known = context_as_started(call, registration.slug, kept.scope, entries, today_in(live.settings.timezone))
    served = await openings.serve_again(session_, live, call, kept, adopt=True, known=known)
    if served is None:
        return None
    catalog = await providers.get_catalog(session_)
    keys = await providers.keys_of(session_, live.vault, kept.scope)
    model = providers.thinking_of(served.declaration, catalog, keys)
    # The session's batches go on from what the log already took from it, never from zero.
    taken = await calls.count_taken(session_, call)
    running = start_session(live, served, model, None, written=taken)
    await session.resume(running, entries)
    await handoff.attach(live.calls, call, registration.owner)
    return running


# What a written call's own log says it opened as, for one that kept no opening: its channel, who
# wrote, the number written to, its day and its contact. What only an opening holds (a persona, what
# it expects, its run, the state it opened in, the call it carries on) such a call never kept. A
# start this version cannot read counts as none: the call is a chat at no number, and goes on.
def context_as_started(call: str, slug: str, scope: Scope, entries: Iterable[Entry], today: date) -> CallContext:
    """The context a written call opened with, as its call.started says it."""
    started = next((entry for entry in entries if entry.type == "call.started"), None)
    try:
        data = None if started is None else CallStarted.parse(started.data, started.type)
    except ValidationError:
        data = None
    caller = "" if data is None else (data.from_ or "")
    # A WhatsApp conversation comes back on its number; a chat at none.
    channel = Channel.web if data is None else Channel(data.channel)
    number = data.to if data is not None and channel.has_a_number else None
    if data is not None:
        today = datetime.fromtimestamp(data.started_at, tz=UTC).date()
    # The contact the call opened with is on its call.started: memory files what it teaches there.
    contact = None if data is None or data.caller is None else Contact(**data.caller.model_dump(exclude_none=True))
    return CallContext(
        call=call,
        channel=channel,
        direction=Direction.inbound,
        caller=caller or call,
        route=Route(org=scope.org, agent=slug, channel=channel, number=number, env=scope.env),
        today=today,
        contact=contact,
        holder=scope.holder or None,
    )


def start_session(
    live: LiveParts, served: Served, model: Running, recalled: tuple[str, ...] | None, *, written: int = 0
) -> session.Session:
    """The session of a written call served here, built and said to run here; not yet started."""
    platform = GatewayPlatform(live, served, recalled)
    call = session.Call(served.context, served.declaration, platform, written=written)
    running = session.open_written(
        call, model, lookup_budget_ms=live.settings.text_lookup_budget_ms, tool_steps=live.settings.max_tool_steps
    )
    live.calls.run(served, running)
    return running


# ── heard ──


def count_tokens(usage: Iterable[ModelUsage]) -> int:
    """The model tokens a call used so far: the llm_tokens quota counts these."""
    return sum(
        (used.input_tokens or 0) + (used.output_tokens or 0) for used in usage if isinstance(used, LLMModelUsage)
    )


# One turn more is admitted before the model is asked. Refused, the org is told once (its alert kept in
# the transaction that found it) and the call ends as a platform's timeout. Until 2026-11 the same
# fourteen lines stood in the chat's endpoint and in the WhatsApp thread.
async def admit_turn(live: LiveParts, running: session.Session) -> QuotaExceeded | None:
    """Admit one more turn of the written call; the refusal, with the call ended, when the org's quota ran out."""
    served = live.calls.find(running.call.context.call)
    if served is None:
        return None
    # The quota is the org's in the env, whoever's copy the call is.
    scope = Scope(served.scope.org, served.scope.env)
    async with live.sessions.begin() as own:
        try:
            await billing.admit_turn(
                own,
                scope.org,
                scope.env,
                turns=running.call.turns,
                tokens=count_tokens(running.usage),
                at=live.store.clock(),
            )
        except QuotaExceeded as refused:
            await live.alerting.credits_exhausted(own, scope, running.call.declaration.slug, refused)
            out = refused
        else:
            return None
    await session.end(running, "timeout", "platform")
    return out


async def hear(live: LiveParts, running: session.Session, text: str) -> QuotaExceeded | None:
    """One written message into the call, its turn admitted first; the refusal when the org's quota ran out."""
    refused = await admit_turn(live, running)
    if refused is None:
        await session.hear(running, text)
    return refused
