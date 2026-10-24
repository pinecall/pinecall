"""Written calls on the gateway: opened on the socket that holds the agent, or taken up again."""

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, date, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from pinecall_runtime.agents.declaration import AgentConfig, Versions
from pinecall_runtime.agents.service import registry, settings
from pinecall_runtime.calls.context import CallContext, Contact, Route
from pinecall_runtime.calls.repository.heads import Claim, HeadRepository
from pinecall_runtime.calls.schemas import LookupRequest, SealCallRequest
from pinecall_runtime.calls.service import openings, visitors
from pinecall_runtime.calls.service.binding import attach
from pinecall_runtime.calls.service.live import Served
from pinecall_runtime.calls.service.seal import seal
from pinecall_runtime.calls.service.serving import Serving, kept_before_served, look_up, serve_call
from pinecall_runtime.enums import Channel, Direction, Opener
from pinecall_runtime.exceptions import Conflict
from pinecall_runtime.judging import service as judging
from pinecall_runtime.kit.auth import Scope
from pinecall_runtime.kit.text import JsonObject
from pinecall_runtime.kit.time import today_in
from pinecall_runtime.providers import service as providers
from pinecall_runtime.session import service as session
from pinecall_runtime.wire.base import Entry
from pinecall_runtime.wire.events import TERMINAL_EVENT, CallStarted
from pinecall_runtime.wire.metrics import LLMModelUsage, ModelUsage
from pinecall_runtime.wire.parts import PlatformTool

# A written call's session runs on one gateway, which says so: another takes it up only once
# that gateway fell silent.
RUNS_ELSEWHERE = "call {call} runs on another gateway: it is taken up there"


@dataclass(frozen=True)
class TextSetup:
    """What a written call runs on: the tuned config, its versions, the model, a golden's facts."""

    config: AgentConfig
    versions: Versions
    model: providers.Running
    # A golden's facts, which recall answers instead of the contact's memory; None on a real call.
    recalled: tuple[str, ...] | None = None


async def open_text(
    session_: AsyncSession, serving: Serving, registration: registry.Registration, context: CallContext
) -> session.Session:
    """A new written call on the socket that holds the agent, admitted and unstarted."""
    scope = registration.scope
    catalog = await providers.get_catalog(session_)
    config, versions = await settings.tuned_for_call(
        session_, registration.config, scope, catalog, settings.Picked(call=context.call)
    )
    model = providers.thinking_of(config, catalog, await providers.keys_of(session_, serving.handles.vault, scope))
    return await open_text_as(session_, serving, registration, context, TextSetup(config, versions, model))


# Admission before the log is claimed: a refused call leaves nothing behind.
async def open_text_as(
    session_: AsyncSession,
    serving: Serving,
    registration: registry.Registration,
    context: CallContext,
    setup: TextSetup,
) -> session.Session:
    """A new written call on this setup, admitted and unstarted."""
    scope = registration.scope
    await visitors.admit_call(session_, serving, scope, registration.slug)
    await serving.logs.store.claim(
        context.call, registration.slug, scope.org, Claim(scope, setup.versions, opened_by=Opener.gateway)
    )
    # Kept as a phone call's is: the gateway holding the app's socket serves it from this.
    await kept_before_served(serving, scope.org, context, setup.config)
    served = serve_call(serving, registration.owner, context, setup.config, scope)
    serving.live.set_opener(context.call, Opener.gateway)
    await serving.live.commands_heard(context.call)
    return _session(serving, served, setup.model, setup.recalled)


# A gateway that restarted forgot the call, not the caller: no admission, no second greeting.
async def resume_text(
    session_: AsyncSession, serving: Serving, registration: registry.Registration, call: str, zone: str
) -> session.Session | None:
    """A written call taken up again from its log; None for one that is over or not this agent's."""
    kept = await HeadRepository(session_).head_of_call(call)
    if kept is None or kept.sealed or kept.scope is None or kept.agent != registration.slug:
        return None
    if serving.live.owners.text_elsewhere(call):
        raise Conflict(RUNS_ELSEWHERE.format(call=call))
    if kept.scope.org != registration.scope.org:
        return None
    # The model reads the tools' arguments as they were sent: the private ones opened.
    entries = await openings.opened_whole(session_, serving.logs.store, serving.handles.vault, call)
    if not entries or any(entry.type == TERMINAL_EVENT for entry in entries):
        return None
    catalog = await providers.get_catalog(session_)
    config, _ = await settings.tuned_for_call(
        session_, registration.config, kept.scope, catalog, settings.Picked(call=call)
    )
    model = providers.thinking_of(config, catalog, await providers.keys_of(session_, serving.handles.vault, kept.scope))
    context = _as_it_opened(call, registration, kept.scope, entries, today_in(zone))
    served = serve_call(serving, None, context, config, kept.scope)
    serving.live.set_opener(call, kept.opened_by)
    await serving.live.commands_heard(call)
    running = _session(serving, served, model, None)
    # The session's batches go on from what the log already took from it, never from zero.
    running.call.writing.after = await serving.logs.store.taken_count(call)
    await session.resume_text(running, session.taken_up(entries))
    await attach(serving.live, call, registration.owner)
    return running


def tokens_of(usage: Iterable[ModelUsage]) -> int:
    """The model tokens a call used so far: the llm_tokens quota counts these."""
    return sum(
        (used.input_tokens or 0) + (used.output_tokens or 0) for used in usage if isinstance(used, LLMModelUsage)
    )


def _session(
    serving: Serving, served: Served, model: providers.Running, recalled: tuple[str, ...] | None
) -> session.Session:
    sessions = serving.handles.sessions

    async def lookup(tool: PlatformTool, arguments: JsonObject, speech: str | None) -> JsonObject:
        async with sessions.begin() as session_:
            return await look_up(session_, serving, served, LookupRequest(tool=tool, input=arguments, speech_id=speech))

    async def sealed(usage: list[ModelUsage], outcome: str) -> None:
        await seal(serving, served, SealCallRequest(usage=usage, outcome=outcome))

    async def hooked() -> None:
        served.hooked.set()

    looking = lookup if recalled is None else judging.golden_lookup(recalled, lookup, served.log.append)
    platform = session.Platform(
        append_many=served.log.append_many, tool=served.tools.run, lookup=looking, seal=sealed, done=hooked
    )
    call = session.Call(served.context, served.config, platform)
    running = session.text_session(
        call, model, serving.handles.settings.text_lookup_budget_ms, serving.handles.settings.max_tool_steps
    )
    serving.live.set_session(served.call, running)
    return running


def _as_it_opened(
    call: str, registration: registry.Registration, scope: Scope, entries: Iterable[Entry], today: date
) -> CallContext:
    started = next((entry for entry in entries if entry.type == "call.started"), None)
    data = None if started is None else CallStarted.model_validate(started.data)
    caller = "" if data is None else (data.from_ or "")
    # A WhatsApp conversation comes back on its number; a chat at none.
    channel = Channel.web if data is None else Channel(data.channel)
    number = data.to if data is not None and channel.has_a_number else None
    route = Route(org=scope.org, agent=registration.slug, channel=channel, number=number, env=scope.env)
    if data is not None:
        today = datetime.fromtimestamp(data.started_at, tz=UTC).date()
    return CallContext(
        call=call,
        channel=channel,
        direction=Direction.inbound,
        caller=caller or call,
        route=route,
        today=today,
        # The contact the call opened with is on its call.started: memory files what it teaches there.
        contact=None if data is None or data.caller is None else Contact(**data.caller.model_dump(exclude_none=True)),
        holder=scope.holder or None,
    )
