"""A simulated caller placed on an agent: admitted, its call claimed or opened, played on its line, its cost kept."""

import logging
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, replace

from sqlalchemy.ext.asyncio import AsyncSession

from runtime.accounts import service as accounts
from runtime.actor import Actor, Scope
from runtime.agents import service as agents
from runtime.billing import service as billing
from runtime.calls import service as calls
from runtime.calls.context import CallContext, Route, new_call_id
from runtime.enums import Channel, Direction, Stage
from runtime.evals.parts import Harness
from runtime.evals.service.briefs import as_scenario, brief_persona
from runtime.evals.service.callers import (
    Heard,
    Improvised,
    caller_stage,
    improvise_line,
    name_of,
    open_caller_model,
    voice_vendor,
)
from runtime.evals.service.leg import describe
from runtime.evals.service.simulated_calls import Simulation, keep_against, play_spoken, play_written
from runtime.evals.tasks import NOT_A_NEW_CALL
from runtime.exceptions import Conflict, QuotaExceeded, TooManyRequests
from runtime.fleet import service as fleet
from runtime.judging import service as judging
from runtime.kit.text import Json, JsonObject
from runtime.kit.time import epoch, today_in
from runtime.live import service as live
from runtime.providers import service as providers
from runtime.providers.stage import Voice
from runtime.session import service as session
from runtime.wire.room import A_SIMULATED_CALLER

logger = logging.getLogger(__name__)

# Placed with every seat of the fleet taken, a spoken call waits through three offers and is answered by
# the overflow's sentence: refused at once instead, which costs nothing and says why.
NO_SEAT = "every seat of the {env}'s fleet holds a call now: ask again in a few seconds, when one ends"
A_SEAT_FREES_S = 10
THE_CALLERS_MODEL = "the caller's model"
LINES_A_MINUTE = 120
TOO_MANY_LINES = "more than 120 caller lines this minute from this org: try again in a minute"


@dataclass(frozen=True, slots=True)
class Scenario:
    """What the caller phones about this run: a goal in the first person, and the facts that goal needs."""

    goal: str
    facts: Mapping[str, str] = field(default_factory=dict[str, str])


@dataclass(frozen=True, slots=True)
class Wanted:
    """What a simulation is placed with: the agent, one of its personas, a written or spoken line, who plays it."""

    agent: str
    persona: str
    # Spoken: a real line, the caller in a voice of its own. Written: the chat the widget has.
    spoken: bool = True
    turns: int = 15
    # Spoken alone: dB of the ambience under the caller's voice, which ambience, the share of packets
    # lost, the silence before each line; each unsaid is the persona's own.
    interferer_db: float | None = None
    packet_loss: float = 0.0
    ambience: str | None = None
    pause_s: float | None = None
    # The model, the voice's vendor and the voice this run alone is played on.
    played_by: judging.Played | None = None
    # What the caller phones about this run, over the persona's goal. Given, a caller of the library
    # is not briefed again.
    scenario: Scenario | None = None


@dataclass(frozen=True, slots=True)
class Started:
    """A simulation placed: the call it plays on, watched like any call."""

    call: str
    spoken: bool


# ── placed ──


# The gateway plays the caller, so the agent is called as anybody calls it: the process that holds it
# answers, and nothing about the agent changes for a simulation. What can be refused is refused before
# the answer: the persona, nobody holding the agent, the calls already on the line, the org's limits,
# a vendor nobody keyed. The conversation is played after it, on a task of this gateway. No session of
# the request's is taken: each read is a transaction of its own, and none is open while a model answers.
# The place on the line is taken before anything that costs: until 2026-11 a caller of the library was
# briefed (a request of the judge model, an eval) before it, so a comparison waiting for a place paid a
# brief at every retry, two seconds apart for up to three quarters of an hour.
async def place_simulation(
    parts: Harness, actor: Actor, wanted: Wanted, *, against: JsonObject, comparison: str | None
) -> Started:
    """Put one of the agent's personas on it, written or spoken; the call it plays on, at once."""
    accounts.check_agent(actor, wanted.agent)
    scope = actor.scope
    async with parts.sessions.begin() as session_:
        persona = await _get_persona(session_, scope, wanted)
        quotas = await billing.get_quotas(session_, scope.org, scope.env)
    registration = parts.apps.get(scope, wanted.agent)
    call = new_call_id()
    # Taken with no await before it, and given back if what follows refuses the call: a burst of
    # requests can never all pass the count together.
    parts.simulations.take_place(call, scope, quotas.simulating_at_most)
    try:
        async with parts.sessions.begin() as session_:
            await admit_simulation(session_, parts, scope, wanted.agent, persona, spoken=wanted.spoken, waits=True)
        caller = await _brief(parts, scope, wanted, persona)
        simulation = Simulation(
            call=call,
            agent=wanted.agent,
            scope=scope,
            persona=caller,
            turns=wanted.turns,
            spoken=wanted.spoken,
            acts=act_as_asked(
                caller.behavior, wanted.interferer_db, wanted.packet_loss, wanted.ambience, wanted.pause_s
            ),
            state=dict(persona.state),
            waits_for_slot=wanted.spoken,
            against=against,
            comparison=comparison,
        )
        if wanted.spoken:
            async with parts.sessions.begin() as session_:
                await claim_new_call(session_, call, wanted.agent, scope)
            parts.simulations.play(call, play_spoken(parts, simulation))
        else:
            running = await open_written_call(parts, registration, simulation)
            parts.simulations.play(call, play_written(parts, running, simulation))
    except BaseException:
        parts.simulations.give_back(call)
        raise
    return Started(call, wanted.spoken)


# Everything that can refuse a simulation is asked here, before a call is claimed or opened: a
# refusal after it left a call nobody hung up and a simulation that was counted (2026-10-23).
async def admit_simulation(
    session_: AsyncSession,
    parts: Harness,
    scope: Scope,
    agent: str,
    persona: judging.Persona | None = None,
    *,
    spoken: bool = False,
    waits: bool = False,
) -> str | None:
    """A simulated call admitted before anything opens, or refused; the model that plays its caller.

    Past the org's simulations is refused with credits.exhausted on the agent's log. A spoken one with
    every slot of the env's fleet taken is refused at once, unless it `waits`: then it is played once
    one frees. A caller whose model, or whose voice when spoken, is on a vendor nobody keyed is refused
    as its run would be.
    """
    if spoken and not waits and not await parts.offering.has_a_slot(await fleet.fleet_of_env(session_, scope.env)):
        raise TooManyRequests(NO_SEAT.format(env=scope.env.value), retry_after_s=A_SEAT_FREES_S)
    try:
        playing = await calls.count_simulating(session_, scope.org, scope.env, at=epoch())
        await billing.admit_simulation(session_, scope.org, scope.env, at=epoch(), playing=playing)
    except QuotaExceeded as refused:
        # Said in a transaction of its own: this one is rolled back with the refusal.
        async with parts.sessions.begin() as own:
            await parts.alerting.credits_exhausted(own, scope, agent, refused)
        raise
    if persona is None:
        return None
    catalog = await providers.get_catalog(session_)
    keys = await providers.keys_of(session_, parts.vault, scope)
    if spoken:
        vendor, model = voice_vendor(catalog, persona)
        providers.stage_on_its_key(Stage.tts, Voice(vendor=vendor, model=model), catalog, keys)
    stage = caller_stage(catalog, keys, persona)
    # A model the vendor lacks is refused before the call opens, as the page says: a persona that
    # names one is tried once here; the catalog's own caller model is known to answer.
    if persona.llm:
        await providers.try_stage(Stage.llm, stage, what=THE_CALLERS_MODEL)
    return name_of(stage)


# A comparison briefs each of its callers once, before any call of it is placed, and hands every call
# what was written: the same caller phones about the same thing under every configuration.
async def write_scenario(parts: Harness, scope: Scope, wanted: Wanted) -> Scenario | None:
    """What a caller of the library phones this agent about, written once; None for one played as written."""
    async with parts.sessions.begin() as session_:
        persona = await _get_persona(session_, scope, wanted)
    briefed = await _brief(parts, scope, wanted, persona)
    return None if briefed is persona else Scenario(briefed.goal, dict(briefed.facts))


# What `live` is handed to admit a chat that names a persona (`live.service.written.Simulations`): a
# chat with a persona is a simulation, admitted before its call opens as the gateway's own are.
class ChatSimulations:
    """A chat's simulated caller admitted: the persona found, played as the chat names, on a vendor somebody keyed."""

    def __init__(self, parts: Harness) -> None:
        self._parts = parts

    async def admit(
        self, session_: AsyncSession, scope: Scope, agent: str, persona: str, played_by: Mapping[str, str] | None
    ) -> live.Simulated:
        """Admit one simulation of the agent's persona, played as named; what it expects, and the model playing it."""
        found = await _find_persona(session_, scope, agent, persona)
        if played_by is not None:
            found = await play_on(session_, found, judging.Played(**played_by), named=frozenset(played_by))
        played = await admit_simulation(session_, self._parts, scope, agent, found)
        return live.Simulated(expects=found.expects, played_by=played)


async def play_on(
    session_: AsyncSession, persona: judging.Persona, played: judging.Played, *, named: frozenset[str]
) -> judging.Persona:
    """The persona as one run plays it, over its own; a model or a voice this box lacks is refused."""
    chosen = {name: getattr(played, name) for name in ("llm", "tts", "voice") if name in named}
    # A voice belongs to its vendor: a run naming another vendor drops the persona's voice.
    if "tts" in chosen and "voice" not in chosen:
        chosen["voice"] = None
    played_by = replace(persona, **chosen)
    catalog = await providers.get_catalog(session_)
    judging.check_persona_models(catalog, played_by.llm, played_by.tts, played_by.voice)
    return played_by


def act_as_asked(
    behavior: judging.Behavior,
    interferer_db: float | None,
    packet_loss: float,
    ambience: str | None = None,
    pause_s: float | None = None,
) -> judging.Behavior:
    """How a caller acts on the line a request names: its noise and its pause, else the persona's own."""
    return replace(
        behavior,
        interferer_db=behavior.interferer_db if interferer_db is None else interferer_db,
        packet_loss=packet_loss or behavior.packet_loss,
        pause_s=behavior.pause_s if pause_s is None else pause_s,
        ambience=behavior.ambience if ambience is None else ambience,
    )


# The head is claimed in the caller's scope before the room is offered, so the worker opens it
# there or not at all, and another org's call can never be named.
async def claim_new_call(session_: AsyncSession, call: str, agent: str, scope: Scope) -> None:
    """Claim a new call in the caller's scope; refused for an id somebody already opened."""
    await refuse_an_opened_call(session_, call)
    await calls.claim_call(session_, call, agent, calls.Claim(scope))


async def refuse_an_opened_call(session_: AsyncSession, call: str) -> None:
    """Refuse a call id somebody already opened: a simulated caller is put on a new one alone."""
    if await calls.find_head(session_, call) is not None:
        raise Conflict(NOT_A_NEW_CALL.format(call=call))


# Opened at once, so a refusal (the org's limits, nobody holding the agent) is the request's; the
# conversation runs after, as long as the caller keeps it going.
async def open_written_call(parts: Harness, registration: live.Registration, simulation: Simulation) -> session.Session:
    """A written call to whoever holds the agent, with what the persona expects on it; unstarted."""
    scope, persona = registration.scope, simulation.persona
    context = CallContext(
        call=simulation.call,
        channel=Channel.web,
        direction=Direction.inbound,
        caller=A_SIMULATED_CALLER,
        persona=persona.name or None,
        expects=tuple(persona.expects),
        route=Route(org=scope.org, agent=registration.slug, channel=Channel.web, env=scope.env),
        today=today_in(parts.settings.timezone),
        holder=scope.holder or None,
        state=dict(simulation.state),
    )
    async with parts.sessions.begin() as session_:
        await refuse_an_opened_call(session_, simulation.call)
        running = await parts.apps.open_written(session_, registration, context, test=simulation.against or None)
    # Committed on its own before the call's first entry: the facts writer rewrites the row whole
    # from what it locked, and a row it did not find yet would be written over.
    await keep_against(parts, simulation)
    return running


async def _get_persona(session_: AsyncSession, scope: Scope, wanted: Wanted) -> judging.Persona:
    persona = await _find_persona(session_, scope, wanted.agent, wanted.persona)
    played = wanted.played_by
    if played is None:
        return persona
    named = frozenset(name for name in ("llm", "tts", "voice") if getattr(played, name) is not None)
    return await play_on(session_, persona, played, named=named)


async def _find_persona(session_: AsyncSession, scope: Scope, agent: str, name: str) -> judging.Persona:
    declaration = await agents.declaration_of(session_, scope, agent)
    class_personas = None if declaration is None else declaration.personas
    return await judging.get_persona(session_, scope.org, agent, name, class_personas)


# The caller phones about what the request says; else a caller of the library is briefed on this agent
# before it phones: what it calls about, in the agent's terms.
async def _brief(parts: Harness, scope: Scope, wanted: Wanted, persona: judging.Persona) -> judging.Persona:
    if wanted.scenario is not None:
        return as_scenario(persona, wanted.scenario.goal, wanted.scenario.facts)
    return await brief_persona(
        parts.sessions,
        parts.vault,
        parts.describers,
        parts.store,
        parts.prompts,
        parts.logs,
        scope,
        wanted.agent,
        persona,
    )


# ── asked by the CLI: a spoken call held to its end, a caller's line, the org's limits ──


@dataclass(frozen=True, slots=True)
class VoiceCall:
    """A spoken call the CLI places and waits for: the room it minted, the agent, the caller, the line."""

    call: str
    agent: str
    persona: judging.Persona
    turns: int = 6
    interferer_db: float | None = None
    packet_loss: float = 0.0
    ambience: str | None = None
    pause_s: float | None = None
    # The state the agent opens the call in: the persona's, as `pinecall simulate` reads it.
    state: JsonObject = field(default_factory=dict[str, Json])


@dataclass(frozen=True, slots=True)
class VoicePlayed:
    """A spoken call played to its end: how many lines the caller said, on what line, what it cost."""

    call: str
    turns: int
    line: str
    caller_cost_usd: float
    # The caller hung up because its call had spent the providers row's `caller.ceiling_usd`.
    stopped_at_ceiling: bool


@dataclass(frozen=True, slots=True)
class Limits:
    """How an org may shape its simulations in an env: the calls at once, those on the line, a comparison's calls."""

    at_once: int
    on_the_line: int
    comparison_calls: int


# The same simulation as `place_simulation` places, on a room the client named, and answered when the
# caller has hung up. A persona is the agent's own or Pinecall's library's: a name that is neither is
# refused; one sent without a name is played as sent. The id is refused before it is given a place:
# until 2026-11 it was admitted first, and an id sent twice took the place of the call playing under it.
async def place_voice_call(parts: Harness, actor: Actor, asked: VoiceCall) -> VoicePlayed:
    """Dispatch the agent into a room, play the persona as a spoken caller, and hang up."""
    accounts.check_agent(actor, asked.agent)
    scope, persona = actor.scope, asked.persona
    async with parts.sessions.begin() as session_:
        if persona.name:
            await _find_persona(session_, scope, asked.agent, persona.name)
        judging.check_persona_models(await providers.get_catalog(session_), persona.llm, persona.tts, persona.voice)
        quotas = await billing.get_quotas(session_, scope.org, scope.env)
        await refuse_an_opened_call(session_, asked.call)
    # A ring with nobody to answer it would wait forty seconds for an agent that never joins.
    parts.apps.get(scope, asked.agent)
    acts = act_as_asked(persona.behavior, asked.interferer_db, asked.packet_loss, asked.ambience, asked.pause_s)
    async with parts.simulations.hold_place(asked.call, scope, quotas.simulating_at_most):
        async with parts.sessions.begin() as session_:
            await admit_simulation(session_, parts, scope, asked.agent, persona, spoken=True)
            await claim_new_call(session_, asked.call, asked.agent, scope)
        simulation = Simulation(
            call=asked.call,
            agent=asked.agent,
            scope=scope,
            persona=persona,
            turns=asked.turns,
            spoken=True,
            acts=acts,
            state=dict(asked.state),
        )
        played = await play_spoken(parts, simulation)
    return VoicePlayed(asked.call, played.turns, describe(acts), played.spending.usd, played.spending.is_over)


# The gateway holds the vendors' keys: the org's own when it brought one, else the box's lent. A
# caller's line is a model call: a call of forty turns says forty, and several run side by side.
async def improvise_next_line(
    parts: Harness, actor: Actor, persona: judging.Persona, heard: Sequence[Heard], turns_left: int
) -> Improvised:
    """The persona's next line on the call so far, improvised by its model; so many a minute for an org."""
    await parts.caller_lines.check(f"{actor.org} evals/caller", TOO_MANY_LINES)
    async with open_caller_model(parts.sessions, parts.vault, actor.scope, persona) as model:
        return await improvise_line(model.model, persona, heard, turns_left)


async def limits_of(session_: AsyncSession, parts: Harness, actor: Actor) -> Limits:
    """How the key's org may shape its simulations in the env: the calls at once, and the calls a comparison places."""
    quotas = await billing.get_quotas(session_, actor.org, actor.env)
    on_the_line = parts.simulations.count(actor.org, actor.env)
    return Limits(quotas.simulating_at_most, on_the_line, quotas.compared_at_most)
