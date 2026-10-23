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
from pydantic import TypeAdapter
from sqlalchemy.ext.asyncio import AsyncSession

from pinecall_runtime.accounts.service import tokens
from pinecall_runtime.agents.declaration import Voice
from pinecall_runtime.agents.service import registry
from pinecall_runtime.alerts import service as alerts
from pinecall_runtime.billing import service as billing
from pinecall_runtime.calls import service as calls
from pinecall_runtime.compliance import service as compliance
from pinecall_runtime.enums import Channel, Direction, Env
from pinecall_runtime.evals.schemas import NextLineRequest, PlayedBy
from pinecall_runtime.evals.service import playing, spoken
from pinecall_runtime.evals.service.callers import Spending, heard_in, improvise_line
from pinecall_runtime.evals.service.players import caller_model, caller_stage, caller_voice, named, voice_vendor
from pinecall_runtime.evals.service.turns import NextLine, is_call_over
from pinecall_runtime.exceptions import Conflict, QuotaExceeded, ServiceUnavailable, TooManyRequests
from pinecall_runtime.fleet import service as fleet
from pinecall_runtime.judging import service as judging
from pinecall_runtime.kit.auth import Scope
from pinecall_runtime.kit.shared_state import SharedState
from pinecall_runtime.kit.text import Json, JsonObject
from pinecall_runtime.kit.time import epoch, today_in
from pinecall_runtime.providers import service as providers
from pinecall_runtime.redis import LocalSignal, Signal
from pinecall_runtime.session import service as session
from pinecall_runtime.wire.dispatch import Dispatch

logger = logging.getLogger(__name__)

NO_LINE = "the simulated call could not be held: {broke}"
# A call id names a room, a log and a recording: a simulated caller is put on a new one alone.
NOT_A_NEW_CALL = "call {call} exists already: a simulated caller is placed on a call id nobody opened"
# Longer than any run, so the caller's token never ends a call first.
A_CALL_MAY_LAST_S = 15 * 60.0
BROKE = "simulated call %s broke"

# The calls a simulated caller may be on at once, per org and env, on every gateway of the box.
# A simulation takes a seat of the fleet beside the real callers and a share of the gateway that
# plays its caller: ten placed in one burst on 2026-10-21 saturated production's two workers and
# sent five callers to the overflow.
AT_ONCE = 3
# The channel each gateway says its simulated calls on, and how often; a change is said at once.
SIMULATING_CHANNEL = "simulating"
SIMULATING_EVERY_S = 1.0
_SIMULATING: TypeAdapter[dict[str, int]] = TypeAdapter(dict[str, int])
TOO_MANY_AT_ONCE = "the org has {playing} simulated calls on the line in {env}, the most at once: wait for one to end"
# How long a caller is told to wait before asking again: about a turn of a call.
ASK_AGAIN_IN_S = 15


class TooManyAtOnce(TooManyRequests):
    """The org has AT_ONCE simulated calls on the line in the env already."""

    def __init__(self, env: Env, playing: int) -> None:
        """Say how many are on the line, and when to ask again."""
        super().__init__(TOO_MANY_AT_ONCE.format(playing=playing, env=env.value), retry_after_s=ASK_AGAIN_IN_S)


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


@dataclass(frozen=True, slots=True)
class Playing:
    """One simulated call on the line: whose it is, and its task when this process plays it apart."""

    scope: Scope
    task: asyncio.Task[None] | None


# Each gateway counts the calls it plays and says the count on the signal, as the calls at once
# are counted: a call takes its place the instant it is admitted, with no await between the
# count and the place, so a burst on one gateway never passes the ceiling; the other gateways'
# counts are heard the instant they change, so a burst split between two may pass it by what
# both admitted in that instant, as concurrent_calls may. A call never counts twice whichever
# gateway its worker reached.
class Simulations:
    """The simulated calls this process plays, and every gateway's count; stopped with the process."""

    def __init__(self, signal: Signal | None = None) -> None:
        """Nothing playing; the other gateways' counts heard on the signal."""
        self.playing: dict[str, Playing] = {}
        self.counted = SharedState(signal or LocalSignal(), SIMULATING_CHANNEL, _SIMULATING, {}, lambda: None)
        self.counted.every_s = SIMULATING_EVERY_S
        self.counted.gathered = self._playing_here

    async def start(self) -> None:
        """Hear the other gateways' counts, and say this one's."""
        await self.counted.start()

    def admit(self, call: str, scope: Scope) -> None:
        """Give the call its place on the line now, or refuse it: the org has AT_ONCE there already."""
        playing = self.on_the_line(scope.org, scope.env)
        if playing >= AT_ONCE:
            raise TooManyAtOnce(scope.env, playing)
        self.playing[call] = Playing(scope, None)
        self._say()

    def release(self, call: str) -> None:
        """Give the call's place back: it was refused after it was admitted, or it ended."""
        if self.playing.pop(call, None) is not None:
            self._say()

    # The request's context goes with the task, so the call is played as the org that asked for it.
    def play(self, call: str, scope: Scope, played: Coroutine[object, object, object]) -> None:
        """Play the admitted call on its own task, kept until it ends; a break is logged, never lost."""

        async def kept() -> None:
            await played

        task = asyncio.create_task(kept())
        self.playing[call] = Playing(scope, task)
        self._say()
        task.add_done_callback(lambda done: self._ended(call, done))

    @asynccontextmanager
    async def admitted(self, call: str, scope: Scope) -> AsyncGenerator[None]:
        """The call's place on the line for the block, which plays it: admitted first, let go after."""
        self.admit(call, scope)
        try:
            yield
        finally:
            self.release(call)

    def on_the_line(self, org: str, env: Env) -> int:
        """How many of the org's simulated calls are on the line in the env, on every gateway."""
        named = _named(org, env)
        theirs = sum(heard.share.get(named, 0) for heard in self.counted.theirs.values())
        return self._playing_here().get(named, 0) + theirs

    async def stop(self) -> None:
        """Stop every call still playing: each one's caller hangs up as its task is cancelled."""
        playing = [one.task for one in self.playing.values() if one.task is not None]
        for task in playing:
            task.cancel()
        await asyncio.gather(*playing, return_exceptions=True)
        await self.counted.close()

    def _ended(self, call: str, done: asyncio.Task[None]) -> None:
        self.release(call)
        if not done.cancelled() and done.exception() is not None:
            logger.error(BROKE, call, exc_info=done.exception())

    def _playing_here(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for one in self.playing.values():
            named = _named(one.scope.org, one.scope.env)
            counts[named] = counts.get(named, 0) + 1
        return counts

    def _say(self) -> None:
        self.counted.put(self._playing_here())


def _named(org: str, env: Env) -> str:
    return f"{org}|{env.value}"


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


# Everything that can refuse a simulation is asked here, before a call is claimed or opened: a
# refusal after it left a call nobody hung up and a simulation that was counted (2026-10-23).
async def admit_simulation(
    session_: AsyncSession,
    serving: calls.Serving,
    scope: Scope,
    agent: str,
    persona: judging.CallerPersona | None = None,
    *,
    voice: bool = False,
) -> str | None:
    """A simulated call admitted before anything opens, or refused; the model that plays its caller.

    Past the org's simulations is refused with credits.exhausted on the agent's log. A caller whose
    model, or whose voice when spoken, is on a vendor nobody keyed is refused as its run would be.
    """
    try:
        playing = await calls.simulating(session_, scope.org, scope.env, at=epoch())
        await billing.admit_simulation(session_, scope.org, scope.env, at=epoch(), playing=playing)
    except QuotaExceeded as refused:
        await alerts.credits_refused(serving, scope, agent, refused)
        raise
    if persona is None:
        return None
    configured = await providers.get_catalog(session_)
    keys = await providers.keys_of(session_, serving.handles.vault, scope)
    if voice:
        vendor, model = voice_vendor(configured, persona)
        providers.stage_on_its_key("tts", Voice(provider=vendor, model=model), configured, keys)
    return named(caller_stage(configured, keys, persona))


async def played_on(session_: AsyncSession, persona: judging.Persona, played: PlayedBy) -> judging.Persona:
    """The persona as one run plays it, over its own; a model or a voice this box lacks is refused."""
    chosen = played.model_dump(exclude_none=True)
    # A voice belongs to its vendor: a run naming another vendor drops the persona's voice.
    if "tts" in chosen and "voice" not in chosen:
        chosen["voice"] = None
    played_by = dataclasses.replace(persona, **chosen)
    judging.check_persona_models(await providers.get_catalog(session_), played_by.llm, played_by.tts, played_by.voice)
    return played_by


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
        notice = await opens_with_a_notice(session_, scope, running.language)
    async with caller_model(serving, scope, persona) as model:
        speech = providers.tts_of(running)
        caller = Caller(persona, model.llm, spending, speech)
        await _played_by(serving, placed.call, model.named, running)
        # The caller murmurs in the language it speaks: the line learns it here, with the voice.
        localised = dataclasses.replace(placed.line, language=running.language)
        line = spoken.SpokenLine("", "", placed.call, placed.turns, localised, notice=notice)
        try:
            turns = await on_the_line(serving, dispatch, speech, line, improvising(serving, placed.call, caller))
        finally:
            await speech.aclose()
            await _kept(serving, placed.call, spending)
    return turns, spending


# The agent says the org's recording notice before its greeting: a caller that did not expect it would
# take it for the opening and talk over the greeting.
async def opens_with_a_notice(session_: AsyncSession, scope: Scope, language: str | None) -> bool:
    """Whether a spoken call of this org opens with a recording notice."""
    policy = (await compliance.policy_of(session_, scope.org)).policy
    return compliance.notice_of(policy, language) is not None


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
