"""What a worker asks of the gateway for its call: opened, opened again, its tools, its judging."""

import base64
import logging

from sqlalchemy.ext.asyncio import AsyncSession

from pinecall_runtime.accounts.service import keys, orgs, tokens
from pinecall_runtime.agents import service as agents
from pinecall_runtime.agents.declaration import AgentConfig, Versions
from pinecall_runtime.agents.service import registry, settings
from pinecall_runtime.calls.context import CallContext
from pinecall_runtime.calls.repository.heads import Claim, HeadRepository
from pinecall_runtime.calls.schemas import OpenCallRequest, OpenCallResponse, RecordingKeyResponse
from pinecall_runtime.calls.service import openings, visitors
from pinecall_runtime.calls.service.binding import attach
from pinecall_runtime.calls.service.live import Served
from pinecall_runtime.calls.service.serving import (
    NO_SUCH_CALL,
    NOT_OPEN,
    SEALED,
    Serving,
    is_the_fleet,
    serve_call,
    serving_agent,
    write_arrival,
)
from pinecall_runtime.channels import service as channels
from pinecall_runtime.compliance import service as compliance
from pinecall_runtime.enums import Direction, Opener
from pinecall_runtime.exceptions import Conflict, Forbidden, NotFound, ValidationError
from pinecall_runtime.kit.auth import Actor, Scope
from pinecall_runtime.kit.crypto import Vault
from pinecall_runtime.providers import service as providers
from pinecall_runtime.session import service as session
from pinecall_runtime.telephony import service as telephony
from pinecall_runtime.wire.base import Entry
from pinecall_runtime.wire.events import ErrorEvent, ToolCall
from pinecall_runtime.wire.parts import ToolResult

logger = logging.getLogger(__name__)

NOT_ITS_ACCOUNT = "{number} lives in another Twilio account than the one this call came from: refused"
NOT_APPROVED = (
    "{number} was hooked by the org and waits for the box's operator to approve it: no call to it opens until then"
)
SPENT = "token_spent"
ALREADY_SPENT = "call {call} was opened by its token already: a token opens one call, once"
ELSEWHERE = "call %s was opened in org %s, %s, agent %s: its token was minted for another"
UNOPENED_KEY = "the key of call {call}'s recording is sealed under a key the vault no longer lists"
NOT_CARRIED = "call {call} carries on {earlier}, which is not its org's and agent's call"
NOT_THIS_ENV = "this key opens {env}, and that call's route answers in {asked}"
NOT_ITS_CONTEXT = "the context is call {named!r}, not {call!r}"
NO_APP_FOR_THE_TOOL = "no app holds agent {slug}: its tools cannot run until one does"


# The log opens before the media, so a console sees the call ring; call.started is the worker's.
async def open_call(session_: AsyncSession, serving: Serving, actor: Actor, body: OpenCallRequest) -> OpenCallResponse:
    """Open a call's log, serve it to its agent's socket, say its minutes and its first words."""
    context = body.context
    keys.check_agent(actor, body.agent)
    scope = call_scope(actor, context)
    if context.direction is Direction.inbound and context.route.number is not None:
        await _check_arrival(session_, serving.handles.vault, scope, context.route.number, body.carrier_account)
    heads = HeadRepository(session_)
    await _check_unclaimed_or_in(heads, context.call, scope)
    await _spend_token(session_, serving, context, scope, body.agent)
    ceiling = await visitors.admit_call(session_, serving, scope, body.agent)
    registration = serving_agent(serving.registry, scope, body.agent, body.app, context)
    _check_served(serving, scope, body, registration)
    config, versions = await _tuned(session_, serving, scope, body.agent, registration, context.call)
    # Asked again by a worker whose gateway died with the answer: the same call, one ringing.
    again = await openings.opening_of(session_, context.call) is not None
    opener = _opener_of(actor)
    await serving.logs.store.claim(context.call, body.agent, scope.org, Claim(scope, versions, opened_by=opener))
    # A worker opened the room's call: nothing is left to offer it to another.
    await serving.offering.forget(context.call)
    await openings.keep_opening(session_, scope.org, context, config)
    await serving.prompts.keep(session_, scope.org, config.knowledge or "")
    served = serve_call(serving, None if registration is None else registration.owner, context, config, scope)
    serving.live.set_opener(context.call, opener)
    await serving.live.commands_heard(context.call)
    if not again:
        await write_arrival(served.log, context, body.agent)
    disclosure, notice = await _opening_words(session_, scope, config.language)
    return OpenCallResponse(
        seconds_left=None if ceiling is None else ceiling.seconds,
        minutes=None if ceiling is None else ceiling.minutes,
        disclosure=disclosure if context.direction is Direction.outbound else None,
        recording_notice=notice,
        history=await _carried(session_, serving, heads, scope, body),
    )


# A gateway that restarted forgot the call: served again from the worker's word, no quota, no
# token, no second call.ringing; the socket holding its agent hears call.attached.
async def reopen_call(session_: AsyncSession, serving: Serving, actor: Actor, call: str, body: OpenCallRequest) -> None:
    """Serve again a call the gateway forgot."""
    if call != body.context.call:
        raise ValidationError(NOT_ITS_CONTEXT.format(named=body.context.call, call=call))
    if call in serving.live.calls:
        return
    scope = call_scope(actor, body.context)
    kept = await HeadRepository(session_).head_of_call(call)
    if kept is None or kept.scope is None:
        raise NotFound(NOT_OPEN.format(call=call))
    if kept.scope != scope:
        raise NotFound(NO_SUCH_CALL.format(call=call))
    if kept.sealed:
        raise Conflict(SEALED.format(call=call))
    registration = serving.registry.serving(scope, body.agent, None)
    config, _ = await _tuned(session_, serving, scope, body.agent, registration, call)
    await openings.keep_opening(session_, scope.org, body.context, config)
    serve_call(serving, None, body.context, config, scope)
    serving.live.set_opener(call, kept.opened_by)
    if registration is not None:
        await attach(serving.live, call, registration.owner)


# The gateway writes tool.call and tool.result: appending the call is what reaches the app.
async def run_tool(serving: Serving, served: Served, agent: str, tool_call: ToolCall) -> ToolResult:
    """Run a worker's tool call through the app that holds its agent, and answer its result."""
    if agent != served.agent:
        raise NotFound(NOT_OPEN.format(call=served.call))
    # Parked because nobody holds the agent: a refusal now, not a wait until the tool's deadline.
    if served.app is None and serving.registry.holder_of(served.scope, agent) is None:
        raise Conflict(NO_APP_FOR_THE_TOOL.format(slug=agent))
    # Its socket is on another gateway, which may never have heard the call was bound to it.
    if served.app is not None and served.app not in serving.live.sockets:
        serving.live.pumped(served.call, after=0)
    use = session.ToolUse(call_id=tool_call.call_id, name=tool_call.name, arguments=dict(tool_call.arguments))
    return await served.tools.run(use, tool_call.speech_id)


# The worker seals the call's recording with it before storing it; asked again, the same key.
async def recording_key_of(session_: AsyncSession, serving: Serving, served: Served) -> RecordingKeyResponse:
    """The key the call's recording is sealed under, made once for the call."""
    found = await compliance.recording_key_for(session_, serving.handles.vault, served.scope.org, served.call)
    if found is None:
        raise Conflict(UNOPENED_KEY.format(call=served.call))
    return RecordingKeyResponse(key=base64.urlsafe_b64encode(found).decode())


async def judging_of(session_: AsyncSession, served: Served) -> agents.JudgingSettings:
    """Whether the call's org judges its calls at hang-up, and the ceiling a judge may spend."""
    on = await orgs.is_judged(session_, served.scope.org)
    return agents.JudgingSettings(on=on, ceiling_usd=providers.judge_ceiling(await providers.get_catalog(session_)))


# A tenant's worker opens its own org's calls in its own env; the fleet's opens any org's in
# its env, in the scope the dispatch named.
def call_scope(actor: Actor, context: CallContext) -> Scope:
    """The scope the call is opened in, as this key may open it."""
    named = Scope(context.route.org, context.env, context.holder or "")
    if is_the_fleet(actor):
        # A fleet serves one env: a unit holding the other env's key is refused here too.
        if named.env is not actor.env:
            raise Forbidden(NOT_THIS_ENV.format(env=actor.env, asked=named.env))
        return named
    if context.route.org != actor.org:
        raise NotFound(NO_SUCH_CALL.format(call=context.call))
    if context.env is not actor.env:
        raise Forbidden(NOT_THIS_ENV.format(env=actor.env, asked=context.env))
    return actor.scope


def _opener_of(actor: Actor) -> Opener:
    return Opener.fleet if is_the_fleet(actor) else Opener.app


# The carrier, the fence and the env rule worked, whatever is refused here. A number the org
# hooked rings nobody until the operator approves it is the org's; a call Twilio sent from an
# account the number does not live in is somebody else's Twilio pointed at it.
async def _check_arrival(
    session_: AsyncSession, vault: Vault, scope: Scope, number: str, came_from: str | None
) -> None:
    await channels.note_called(session_, scope.org, number)
    record = await telephony.record_of(session_, scope.org, number)
    if record is not None and not record.route.approved:
        raise Forbidden(NOT_APPROVED.format(number=number))
    if came_from is None:
        return
    expected = await telephony.twilio_account_of(session_, vault, scope.org, number)
    if expected is not None and expected != came_from:
        raise Forbidden(NOT_ITS_ACCOUNT.format(number=number))


# A call a dial placed already has its head: the worker opens it in the scope the head keeps, or
# not at all, whatever its key; the first claim of a head stands, so this is the one check.
async def _check_unclaimed_or_in(heads: HeadRepository, call: str, scope: Scope) -> None:
    kept = await heads.head_of_call(call)
    if kept is not None and kept.scope is not None and kept.scope != scope:
        raise NotFound(NO_SUCH_CALL.format(call=call))


# A web call opens by the token its room was minted with: once, and only in the org, the env
# and for the agent it was minted for. Asked of the ledger by the call's id, whatever the worker
# says: a call no token was minted for (a phone, a dial, a run) is not a token's to refuse.
async def _spend_token(
    session_: AsyncSession, serving: Serving, context: CallContext, scope: Scope, agent: str
) -> None:
    spending = await tokens.spend_token(session_, context.call, scope, agent)
    if spending in {"spent", "never_minted"}:
        return
    if spending == "minted_elsewhere":
        logger.warning(ELSEWHERE, context.call, scope.org, scope.env, agent)
        raise NotFound(NO_SUCH_CALL.format(call=context.call))
    sentence = ALREADY_SPENT.format(call=context.call)
    refused = ErrorEvent(code=SPENT, message=sentence, recoverable=True)
    await serving.logs.agent(agent).append("error", refused.dump())
    raise Conflict(sentence)


def _check_served(
    serving: Serving, scope: Scope, body: OpenCallRequest, registration: registry.Registration | None
) -> None:
    if body.app is not None and registration is None:
        raise registry.NotThatApp(body.app, body.agent)
    # Held by consoles alone: refused before the greeting, rather than a call with no app.
    if registration is None and serving.registry.holder_of(scope, body.agent) is not None:
        raise registry.NobodyTakes(body.agent)


# The call's id picks its version where the scope stands on a canary, the same on a reopen.
async def _tuned(
    session_: AsyncSession,
    serving: Serving,
    scope: Scope,
    agent: str,
    registration: registry.Registration | None,
    call: str,
) -> tuple[AgentConfig, Versions]:
    declared = serving.registry.holder_of(scope, agent) if registration is None else registration
    config = AgentConfig(slug=agent) if declared is None else declared.config
    catalog = await providers.get_catalog(session_)
    return await settings.tuned_for_call(session_, config, scope, catalog, settings.Picked(call=call))


# The worker says the disclosure before the greeting, and the notice only where it records.
async def _opening_words(session_: AsyncSession, scope: Scope, language: str | None) -> tuple[str | None, str | None]:
    kept = (await compliance.policy_of(session_, scope.org)).policy
    org = await orgs.find_org(session_, scope.org)
    name = scope.org if org is None else org.name
    return compliance.disclosure_of(kept, name, language), compliance.notice_of(kept, language)


# The call carried on must be the same org's, env's and agent's, whatever the worker says.
async def _carried(
    session_: AsyncSession, serving: Serving, heads: HeadRepository, scope: Scope, body: OpenCallRequest
) -> list[Entry]:
    earlier = body.context.continues
    if earlier is None:
        return []
    kept = await heads.head_of_call(earlier)
    if kept is None or kept.scope != scope or kept.agent != body.agent:
        raise NotFound(NOT_CARRIED.format(call=body.context.call, earlier=earlier))
    return await openings.carried(session_, serving.logs.store, serving.handles.vault, earlier)
