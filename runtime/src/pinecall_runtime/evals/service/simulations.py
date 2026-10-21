"""A simulated caller on a call: a new call claimed for it, its model, its voice, its lines, spoken or written."""

import asyncio
import dataclasses
import logging
from collections.abc import AsyncGenerator, Coroutine
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import Never

from livekit import rtc
from livekit.agents import llm, tts
from sqlalchemy.ext.asyncio import AsyncSession

from pinecall_runtime.accounts.service import tokens
from pinecall_runtime.agents.declaration import AgentConfig, Model, Voice
from pinecall_runtime.agents.service import registry, settings, tuning
from pinecall_runtime.alerts import service as alerts
from pinecall_runtime.billing import service as billing
from pinecall_runtime.calls import service as calls
from pinecall_runtime.enums import Channel, Direction, Env
from pinecall_runtime.evals.schemas import NextLineRequest
from pinecall_runtime.evals.service import playing, spoken
from pinecall_runtime.evals.service.callers import Spending, heard_in, improvise_line
from pinecall_runtime.evals.service.turns import NextLine, is_call_over
from pinecall_runtime.exceptions import Conflict, PinecallError, QuotaExceeded, ServiceUnavailable
from pinecall_runtime.fleet import service as fleet
from pinecall_runtime.judging import service as judging
from pinecall_runtime.kit.auth import Scope
from pinecall_runtime.kit.text import Json, JsonObject
from pinecall_runtime.kit.time import epoch, today_in
from pinecall_runtime.providers import service as providers
from pinecall_runtime.session import service as session
from pinecall_runtime.wire.dispatch import Dispatch

logger = logging.getLogger(__name__)

NO_LINE = "the simulated call could not be held: {broke}"
# A call id names a room, a log and a recording: a simulated caller is put on a new one alone.
NOT_A_NEW_CALL = "call {call} exists already: a simulated caller is placed on a call id nobody opened"
# Longer than any run, so the caller's token never ends a call first.
A_CALL_MAY_LAST_S = 15 * 60.0
# A vendor that would not list its voices: the caller speaks in its plugin's own, the agent's too.
NONE_LISTED = "%s listed no voice for a simulated caller to speak in: it speaks in the plugin's own"
BROKE = "simulated call %s broke"


@dataclass(frozen=True, slots=True)
class Caller:
    """Who plays a simulated call: the persona, its model, what it has spent, its voice spoken."""

    persona: judging.CallerPersona
    model: llm.LLM[Never]
    spending: Spending
    speech: tts.TTS[Never] | None = None


@dataclass(frozen=True)
class Placed:
    """A simulated call to place: its id, the agent, who plays it, how long, on what line."""

    call: str
    agent: str
    persona: judging.CallerPersona
    turns: int
    line: spoken.Line = field(default_factory=spoken.Line)
    state: JsonObject = field(default_factory=dict[str, Json])


class Simulations:
    """The simulated calls this process plays after their endpoint answered; stopped with the process."""

    def __init__(self) -> None:
        """Nothing playing."""
        self.playing: dict[str, asyncio.Task[None]] = {}

    # The request's context goes with the task, so the call is played as the org that asked for it.
    def play(self, call: str, played: Coroutine[object, object, object]) -> None:
        """Play the call on its own task, kept until it ends; a break is logged, never lost."""

        async def kept() -> None:
            await played

        task = asyncio.create_task(kept())
        self.playing[call] = task
        task.add_done_callback(lambda done: self._ended(call, done))

    async def stop(self) -> None:
        """Stop every call still playing: each one's caller hangs up as its task is cancelled."""
        playing = list(self.playing.values())
        for task in playing:
            task.cancel()
        await asyncio.gather(*playing, return_exceptions=True)

    def _ended(self, call: str, done: asyncio.Task[None]) -> None:
        self.playing.pop(call, None)
        if not done.cancelled() and done.exception() is not None:
            logger.error(BROKE, call, exc_info=done.exception())


def calling_as(persona: judging.Persona) -> judging.CallerPersona:
    """The persona as the caller is played: who, how, what it knows, expects, and how it acts."""
    return judging.CallerPersona(
        name=persona.name,
        goal=persona.goal,
        style=persona.style,
        facts=dict(persona.facts),
        llm=persona.llm,
        tts=persona.tts,
        voice=persona.voice,
        expects=list(persona.expects),
        behavior=judging.CallerBehavior.model_validate(dataclasses.asdict(persona.behavior)),
    )


async def admit_simulation(session_: AsyncSession, serving: calls.Serving, scope: Scope, agent: str) -> None:
    """A simulated call admitted, or refused with credits.exhausted on the agent's log."""
    try:
        await billing.admit_simulation(session_, scope.org, scope.env, at=epoch())
    except QuotaExceeded as refused:
        await alerts.credits_exhausted(session_, serving.handles, serving.logs, scope, agent, refused)
        raise


# The head is claimed in the caller's scope before the room is offered, so the worker opens it
# there or not at all, and another org's call can never be named.
async def claim_new_call(session_: AsyncSession, serving: calls.Serving, call: str, agent: str, scope: Scope) -> None:
    """Claim a new call in the caller's scope; refused for an id somebody already opened."""
    await refuse_an_opened_call(session_, call)
    await serving.logs.store.claim(call, agent, scope.org, calls.Claim(scope))


async def refuse_an_opened_call(session_: AsyncSession, call: str) -> None:
    """Refuse a call id somebody already opened: a simulated caller is put on a new one alone."""
    if await calls.head_of_call(session_, call) is not None:
        raise Conflict(NOT_A_NEW_CALL.format(call=call))


# ── the caller ──


@dataclass(frozen=True, slots=True)
class CallerModel:
    """The model a caller's lines are improvised on, and its `vendor/model` as it runs."""

    llm: llm.LLM[Never]
    named: str


def named(stage: providers.Running) -> str:
    """A stage as it runs, `vendor/model`, or the vendor alone on its plugin's own model."""
    return stage.vendor if not stage.model else f"{stage.vendor}/{stage.model}"


# Read in a transaction of its own: the model is held for a whole call, and no connection is.
@asynccontextmanager
async def caller_model(
    serving: calls.Serving, scope: Scope, persona: judging.CallerPersona
) -> AsyncGenerator[CallerModel]:
    """The model that improvises the caller's lines: the persona's, else the box's caller's."""
    async with serving.handles.sessions.begin() as session_:
        configured = await providers.get_catalog(session_)
        keys = await providers.keys_of(session_, serving.handles.vault, scope)
    row = None if configured.caller is None else configured.caller.llm
    declared = tuning.model_named(persona.llm or None, "llm", in_use=configured.default_vendors["llm"]) or (
        None if row is None else Model(provider=row.vendor, model=row.model or "")
    )
    stage = providers.stage_on_its_key("llm", declared, configured, keys)
    model = providers.llm_of(stage)
    try:
        yield CallerModel(model, named(stage))
    finally:
        await model.aclose()


# The caller speaks in the agent's language and never in the agent's own voice.
async def caller_voice(
    session_: AsyncSession, serving: calls.Serving, scope: Scope, agent: str, persona: judging.CallerPersona | None
) -> providers.Running:
    """The caller's voice: the persona's, else one of the vendor's that is not the agent's."""
    configured = await providers.get_catalog(session_)
    holding = serving.registry.serving(scope, agent, None)
    config = AgentConfig(slug=agent)
    if holding is not None and holding.scope.org == scope.org:
        config, _ = await settings.tuned_for_call(session_, holding.config, holding.scope, configured)
    in_use = configured.default_vendors["tts"]
    named = None if persona is None else tuning.model_named(persona.tts or None, "tts", in_use=in_use)
    vendor = in_use if named is None else named.provider
    model = None if named is None else named.model or None
    keys = await providers.keys_of(session_, serving.handles.vault, scope)
    agents = _voice_the_agent_speaks(config, configured, keys, vendor)
    chosen = spoken.pick_caller_voice(
        configured.voices, vendor, agents, config.language, None if persona is None else persona.voice
    )
    unnamed = providers.stage_on_its_key("tts", Voice(provider=vendor, model=model), configured, keys)
    if chosen is None:
        chosen = await _another_listed(configured, unnamed, agents, config.language)
    stage = providers.stage_on_its_key("tts", Voice(provider=vendor, model=model, voice_id=chosen), configured, keys)
    return dataclasses.replace(stage, voice=chosen, language=config.language)


# The caller leaving ends the call as a hang-up, which the worker writes; the room is deleted after,
# whatever happened, so a worker that never noticed still ends its job and seals the log. The call
# lasts minutes, and holds no connection: the fleet is read and the transaction is over.
HANGS_UP_WITHIN_S = 10.0


async def on_the_line(
    serving: calls.Serving,
    dispatch: Dispatch,
    speech: tts.TTS[Never],
    line: spoken.SpokenLine,
    next_line: NextLine,
) -> int:
    """Offer the agent the room, put the caller on it, and play its lines; the lines said."""
    env = dispatch.env or Env.sandbox
    async with serving.handles.sessions.begin() as session_:
        the_fleet = await fleet.fleet_of_env(session_, env)
    visitor = tokens.Visitor(expires_at=epoch() + A_CALL_MAY_LAST_S, identity=judging.A_SIMULATED_CALLER)
    token = tokens.room_token(serving.signer, line.call, "talk", visitor)
    joined = dataclasses.replace(line, url=serving.handles.settings.livekit_url_of(env), token=token)
    try:
        await serving.offering.offer(line.call, the_fleet, dispatch)
        said = await spoken.run_spoken(joined, speech, serving.logs, next_line)
    except (TimeoutError, rtc.ConnectError) as broke:
        raise ServiceUnavailable(NO_LINE.format(broke=broke)) from broke
    else:
        await _hung_up(serving, line.call)
        return said
    finally:
        await fleet.close_room(serving.handles.servers[env], line.call)


async def _hung_up(serving: calls.Serving, call: str) -> None:
    """Wait, briefly, for the worker to write the call's end once its caller left."""
    log = serving.logs.reading(call)
    subscription = await log.follow()
    try:
        async with asyncio.timeout(HANGS_UP_WITHIN_S):
            while (await log.snapshot()).status != "ended":
                await anext(subscription, None)
    except TimeoutError:
        logger.info("%s: the worker wrote no call.ended within %.0f s; its room is closed", call, HANGS_UP_WITHIN_S)
    finally:
        subscription.close()


# Asked before each line: the line that crosses the ceiling is the last one said, and a call the
# agent or a person already ended asks for none. Spoken, the voice is counted with the line.
def improvising(serving: calls.Serving, call: str, caller: Caller) -> NextLine:
    """The caller's next line on the call so far, and whether it hangs up after it."""

    async def improvised(turns_left: int) -> tuple[str, bool]:
        entries = await serving.logs.store.whole(call)
        if is_call_over(entries) or caller.spending.is_over:
            return "", True
        request = NextLineRequest(persona=caller.persona, heard=heard_in(entries), turns_left=turns_left)
        next_one = await improvise_line(caller.model, request)
        caller.spending.count(next_one, caller.speech)
        return next_one.answer.say, next_one.answer.hangup

    return improvised


# The agent is dispatched into a room whoever holds it — a process deployed or a developer's —
# and the caller speaks there in a voice of its own; the room going ends the job, which seals it.
async def spoken_call(serving: calls.Serving, scope: Scope, placed: Placed) -> tuple[int, Spending]:
    """Play the persona out loud on the agent's line; the lines said, and what they cost."""
    persona = placed.persona
    dispatch = Dispatch(
        agent=placed.agent,
        org=scope.org,
        env=scope.env,
        holder=scope.holder or None,
        caller=judging.A_SIMULATED_CALLER,
        persona=persona.name or None,
        expects=list(persona.expects),
        state=dict(placed.state),
    )
    async with serving.handles.sessions.begin() as session_:
        spending = Spending(await providers.get_catalog(session_))
        running = await caller_voice(session_, serving, scope, placed.agent, persona)
    async with caller_model(serving, scope, persona) as model:
        speech = providers.tts_of(running)
        caller = Caller(persona, model.llm, spending, speech)
        await _played_by(serving, placed.call, model.named, running)
        # The caller murmurs in the language it speaks: the line learns it here, with the voice.
        localised = dataclasses.replace(placed.line, language=running.language)
        line = spoken.SpokenLine("", "", placed.call, placed.turns, localised)
        try:
            turns = await on_the_line(serving, dispatch, speech, line, improvising(serving, placed.call, caller))
        finally:
            await speech.aclose()
            await _kept(serving, placed.call, spending)
    return turns, spending


# Opened at once, so a refusal — the org's limits, nobody holding the agent — is the request's;
# the conversation runs after, as long as the caller keeps it going.
async def written_call(
    session_: AsyncSession, serving: calls.Serving, registration: registry.Registration, placed: Placed
) -> session.Session:
    """A written call to whoever holds the agent, with what the persona expects on it; unstarted."""
    scope, persona = registration.scope, placed.persona
    await refuse_an_opened_call(session_, placed.call)
    context = calls.CallContext(
        call=placed.call,
        channel=Channel.web,
        direction=Direction.inbound,
        caller=judging.A_SIMULATED_CALLER,
        persona=persona.name or None,
        expects=tuple(persona.expects),
        route=calls.Route(org=scope.org, agent=registration.slug, channel=Channel.web, env=scope.env),
        today=today_in(serving.handles.settings.timezone),
        holder=scope.holder or None,
        state=dict(placed.state),
    )
    return await calls.open_text(session_, serving, registration, context)


async def written_turns(serving: calls.Serving, running: session.Session, placed: Placed) -> tuple[int, Spending]:
    """The persona's lines said on the written call, until it hangs up; and what they cost."""
    route = running.call.context.route
    async with serving.handles.sessions.begin() as session_:
        spending = Spending(await providers.get_catalog(session_))
    async with caller_model(serving, Scope(route.org, route.env), placed.persona) as model:
        caller = Caller(placed.persona, model.llm, spending)
        await _played_by(serving, placed.call, model.named, None)
        try:
            lines = await playing.converse(
                running, serving.logs, improvising(serving, placed.call, caller), placed.turns
            )
        finally:
            await _kept(serving, placed.call, spending)
    return lines, spending


# Kept as the call starts, so the call's page names who plays the caller while it plays.
async def _played_by(serving: calls.Serving, call: str, model: str, voice: providers.Running | None) -> None:
    tts, chosen = (None, None) if voice is None else (named(voice), voice.voice)
    async with serving.handles.sessions.begin() as session_:
        await calls.keep_caller_played(session_, call, llm=model, tts=tts, voice=chosen)


# Kept whatever ended the call, a caller hanging up or the line failing: what it spent was spent.
async def _kept(serving: calls.Serving, call: str, spending: Spending) -> None:
    async with serving.handles.sessions.begin() as session_:
        await calls.keep_caller_cost(session_, call, spending.usd)


# The voice the agent speaks with on the caller's vendor: the one it declared, else the operator's
# for its language, else its plugin's own default, which is what its pipeline gives it; on another
# vendor no voice of the caller's can be the agent's.
def _voice_the_agent_speaks(
    config: AgentConfig, configured: providers.Catalog, keys: providers.Keyring, vendor: str
) -> str | None:
    declared = config.voice or Voice(provider=configured.default_vendors["tts"])
    if declared.provider != vendor:
        return None
    row = configured.voices.get(f"{vendor}/{providers.primary_language(config.language)}")
    if declared.voice_id or row:
        return declared.voice_id or row
    return providers.default_voice(providers.stage_on_its_key("tts", declared, configured, keys))


# The operator gave no voice the agent is not speaking in: the vendor's own, the row's listing
# first, in the agent's language before any other. A vendor that lists none leaves the plugin's.
async def _another_listed(
    configured: providers.Catalog, unnamed: providers.Running, agents: str | None, language: str | None
) -> str | None:
    spoken_in = providers.primary_language(language)
    try:
        listed = providers.listed_in_catalog(configured, unnamed.vendor, spoken_in) or await providers.listed_by_vendor(
            dataclasses.replace(unnamed, language=spoken_in)
        )
    except PinecallError:
        logger.warning(NONE_LISTED, unnamed.vendor, exc_info=True)
        return None
    others = [voice for voice in listed if voice.id != agents]
    same_language = [voice for voice in others if _speaks(voice, spoken_in)]
    found = (same_language or others)[:1]
    return found[0].id if found else None


def _speaks(voice: providers.ListedVoice, language: str | None) -> bool:
    its_own = str(voice.detail.get("language") or "")
    return language is None or its_own == "" or its_own.startswith(language)
