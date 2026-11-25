"""A simulated call: played on its line by a caller of its own, what that cost and how it was heard kept with it."""

import logging
from collections.abc import AsyncGenerator, Mapping, Sequence
from contextlib import asynccontextmanager
from dataclasses import asdict, dataclass, field, replace
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from runtime.actor import Actor, Scope
from runtime.agents import service as agents
from runtime.agents.declaration import Declaration
from runtime.calls import folds
from runtime.calls import service as calls
from runtime.calls.log import Store
from runtime.compliance import service as compliance
from runtime.evals.parts import CallerParts, Harness
from runtime.evals.service import hearing, lines
from runtime.evals.service.callers import (
    Caller,
    Spending,
    caller_voice,
    improvise_line,
    list_heard,
    name_of,
    open_caller_model,
    stage_of_caller,
)
from runtime.evals.service.leg import Spoken
from runtime.evals.service.phone import PhoneLine
from runtime.evals.service.spoken import SpokenLine
from runtime.evals.service.turns import NextLine, is_call_over
from runtime.evals.service.written import WrittenLine
from runtime.exceptions import PinecallError
from runtime.judging import service as judging
from runtime.kit.crypto import Vault
from runtime.kit.link import LinkShape
from runtime.kit.loops import is_cancellation, survive
from runtime.kit.text import Json, JsonObject
from runtime.postgres import when_free
from runtime.providers import service as providers
from runtime.providers.catalog import Catalog
from runtime.providers.stage import Running
from runtime.session import service as session
from runtime.wire.dispatch import Dispatch
from runtime.wire.room import A_SIMULATED_CALLER

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class Simulation:
    """A simulated call to play: its id, the agent, in whose scope, who plays it, how long, on what line."""

    call: str
    agent: str
    scope: Scope
    persona: judging.Persona
    turns: int
    spoken: bool
    # How the caller acts on the line, the request's noise and pause over the persona's own.
    acts: judging.Behavior
    state: JsonObject = field(default_factory=dict[str, Json])
    # Spoken with no slot free: wait for the fleet to grow rather than refuse at once.
    waits_for_slot: bool = False
    # The voice and models the agent runs on for this call alone, checked as a test room's are; and the
    # comparison the call was placed in, with the others of its persona.
    against: JsonObject = field(default_factory=dict[str, Json])
    comparison: str | None = None
    # Spoken alone: the network the caller's packets cross, and the number it rings when it reaches
    # the agent by phone, over SIP; None for a caller that joins the agent's room.
    network: LinkShape = field(default_factory=LinkShape)
    rings: str | None = None
    # Spoken alone: the scope of the app that holds the agent, where one of the caller's org does. Said by
    # the gateway that placed the call, which knows who holds each agent: the process that plays the
    # caller picks its voice against the agent as that app runs it, and may be one that serves no app.
    held_by: Scope | None = None


@dataclass(frozen=True, slots=True)
class Played:
    """A simulated call played to its end: the lines its caller said, and what they cost."""

    turns: int
    spending: Spending


# The agent is dispatched into a room whoever holds it, and the caller speaks there in a voice of its
# own: seated in that room, or, when it rings a number, through a phone leg dialled into it. Played by
# whichever process holds the caller: what breaks it before the call began is its caller's to say
# (`ending_what_never_began` on a gateway, the job's row in a process that claimed it). How the leg kept
# to the clock is kept with the call whatever ended it.
async def play_spoken(parts: CallerParts, simulation: Simulation) -> Played:
    """Play the persona out loud on the agent's line; the lines said, and what they cost."""
    voice, notice = await when_free(lambda: _read_voice(parts, simulation))
    # The caller murmurs in the language it speaks: the line learns it here, with the voice.
    spoken = Spoken(simulation.call, simulation.acts, voice.language, notice, simulation.network)
    on_the_line = SpokenLine if simulation.rings is None else PhoneLine
    line = on_the_line(parts, _dispatch_of(simulation), voice, spoken, waits_for_slot=simulation.waits_for_slot)
    try:
        return await play(parts.sessions, parts.vault, parts.store, simulation, line, voice)
    finally:
        pace = line.read_pace()
        if pace is not None:
            await when_free(lambda: keep_line(parts.sessions, simulation.call, pace))


async def play_written(parts: Harness, running: session.Session, simulation: Simulation) -> Played:
    """The persona's lines said on the written call, until it hangs up; and what they cost."""
    async with ending_what_never_began(parts, simulation):
        line = WrittenLine(running, parts.logs, parts.store)
        return await play(parts.sessions, parts.vault, parts.store, simulation, line, None)


# A simulated call is played on a task nobody awaits: what breaks it is logged by the gateway and seen
# by no reader. A call that never began has nobody to end it either: its row would stay open, and
# whoever follows it, a command or a comparison counting its calls, would wait for good. So whatever
# breaks the caller before the call began ends the call, saying why, as a call no worker took is ended
# (`end_never_served`: the reason on its log, its end, its summary). Until 2026-11-25 this was done for
# a seat never got and a line that could not be held, and nothing else: a caller the database had no
# connection for, or one whose vendor refused its model, left its call open and unsaid. A call that
# began is its agent's to end: the caller's line closes its room as it breaks.
@asynccontextmanager
async def ending_what_never_began(
    parts: Harness, simulation: Simulation, *, doing: str = "play this call's caller"
) -> AsyncGenerator[None]:
    """Play a simulated call in the block; one that breaks before the call began is ended, saying why."""
    try:
        yield
    except Exception as broke:
        if not is_cancellation(broke):
            with survive("ending a simulated call that never began", simulation.call):
                entries = await when_free(lambda: parts.store.whole_of(simulation.call))
                if not any(entry.type == "call.started" for entry in entries):
                    await parts.apps.end_never_served(simulation.call, simulation.agent, say_why(broke, doing))
        raise


# A refusal of ours is said in its own words. Anything else is the gateway's own fault, named by its
# kind alone: a database error's text carries the statement it was on.
def say_why(broke: BaseException, doing: str) -> str:
    """Why something of a simulated call broke, as its reader is told."""
    if isinstance(broke, PinecallError):
        return str(broke)
    return f"the gateway could not {doing} ({type(broke).__name__}): its log says why"


def _dispatch_of(simulation: Simulation) -> Dispatch:
    scope, persona = simulation.scope, simulation.persona
    return Dispatch(
        agent=simulation.agent,
        org=scope.org,
        env=scope.env,
        holder=scope.holder or None,
        caller=A_SIMULATED_CALLER,
        persona=persona.name or None,
        expects=list(persona.expects),
        state=dict(simulation.state),
        tuning=dict(simulation.against),
        dialled=simulation.rings,
    )


async def _read_voice(parts: CallerParts, simulation: Simulation) -> tuple[Running, bool]:
    scope = simulation.scope
    async with parts.sessions.begin() as session_:
        agent = await agent_as_it_runs(session_, simulation.held_by, simulation.agent)
        voice = await caller_voice(session_, parts.vault, scope, agent, simulation.persona)
        return voice, await opens_with_a_notice(session_, scope)


async def _read_catalog(sessions: async_sessionmaker[AsyncSession]) -> Catalog:
    async with sessions.begin() as session_:
        return await providers.get_catalog(session_)


# The one skeleton of a simulated call, whatever line it is on. Until 2026-11 it was written twice, a
# spoken and a written one, and a third time for a golden said out loud, which forgot what the caller
# spent and how it was heard. What was spent is kept whatever ended the call, a caller hanging up or
# the line failing: it was spent. Only a simulation knows what its caller really said and when: how the
# agent heard it is measured against that once the caller has left, and kept with the call's facts.
# Nobody waits on the task that plays it, so each thing it asks the database is asked again when the
# pool is full (`when_free`): a request would be answered "busy", and this has nobody to tell.
async def play(
    sessions: async_sessionmaker[AsyncSession],
    vault: Vault,
    store: Store,
    simulation: Simulation,
    line: lines.Line,
    voice: Running | None,
) -> Played:
    """Play the simulation on its line: who plays it kept as it starts, its lines said, its cost and hearing kept."""
    scope, call = simulation.scope, simulation.call
    spending = Spending(await when_free(lambda: _read_catalog(sessions)))
    stage = await when_free(lambda: stage_of_caller(sessions, vault, scope, simulation.persona))
    async with open_caller_model(stage) as model:
        caller = Caller(simulation.persona, model.model, spending)
        await when_free(lambda: _keep_played_by(sessions, call, model.named, voice))
        try:
            turns = await lines.play(line, simulation.turns, improvise(line, caller), spending.count)
        finally:
            await when_free(lambda: keep_cost(sessions, call, spending))
            await when_free(lambda: keep_heard(sessions, store, call, line.list_said()))
    return Played(turns, spending)


# Asked before each line: the line that crosses the ceiling is the last one said, and a call the
# agent or a person already ended asks for none.
def improvise(line: lines.Line, caller: Caller) -> NextLine:
    """The caller's next line on the call so far, and whether it hangs up after it."""

    async def next_line(turns_left: int) -> tuple[str, bool]:
        entries = await line.read_so_far()
        if is_call_over(entries) or caller.spending.is_over:
            return "", True
        said = await improvise_line(caller.model, caller.persona, list_heard(entries), turns_left)
        caller.spending.count(said.usage)
        return said.say, said.hangup

    return next_line


# The agent as a call of the scope runs it, where an app of the org holds it: what the caller's voice is
# picked against (its language, the voice it speaks in).
async def agent_as_it_runs(session_: AsyncSession, held_by: Scope | None, agent: str) -> Declaration | None:
    """The agent's declaration over the settings of the app that holds it; None when no app of the org does."""
    if held_by is None:
        return None
    catalog = await providers.get_catalog(session_)
    of_its_class = (await agents.agent_of(session_, held_by, agent)).whole
    return (await agents.resolve_for_call(session_, of_its_class, held_by, catalog)).declaration


# Asked of the gateway's live side as a call is placed, for the simulation to carry.
def holder_of(parts: Harness, scope: Scope, agent: str) -> Scope | None:
    """The scope of the app that holds the agent for a call of this scope, where one of its org does."""
    held = parts.apps.find(scope, agent)
    return None if held is None or held.scope.org != scope.org else held.scope


# The agent says the org's recording notice before its greeting: a caller that did not expect it would
# take it for the opening and talk over the greeting.
async def opens_with_a_notice(session_: AsyncSession, scope: Scope) -> bool:
    """Whether a spoken call of this org opens with a recording notice."""
    return (await compliance.policy_of(session_, scope.org)).recording_notice


# Kept as the call starts, so the call's page names who plays the caller while it plays.
async def _keep_played_by(
    sessions: async_sessionmaker[AsyncSession], call: str, model: str, voice: Running | None
) -> None:
    tts, chosen = (None, None) if voice is None else (name_of(voice), voice.voice)
    async with sessions.begin() as session_:
        await calls.keep_caller_played(session_, call, llm=model, tts=tts, voice=chosen)


# A call is its comparison's from the transaction that makes it a call, with how it was placed: all of
# it or none. Until 2026-11-25 what the agent ran on and the comparison were kept by the task that
# plays the call, in a transaction of its own: when that one found no connection (twenty calls placed
# together on a pool of eight) the call existed, claimed and counted on the org's line, and was no row
# of its comparison, whose table then said nineteen of twenty with nothing waiting and nothing refused.
async def keep_as_placed(session_: AsyncSession, simulation: Simulation, placed: JsonObject, persona: str) -> None:
    """Keep with the call's facts how it was placed, what its agent runs on for it alone, and its comparison."""
    await calls.keep_how_placed(session_, simulation.call, placed, persona=persona)
    if simulation.against or simulation.comparison is not None:
        await calls.keep_agent_values(
            session_,
            simulation.call,
            against=simulation.against or None,
            comparison=simulation.comparison,
            persona=simulation.persona.name,
        )


# A written call is open by then, on the org's line: one that cannot be kept as placed is ended, saying
# why, never left there with nobody to play it.
async def keep_written_as_placed(parts: Harness, simulation: Simulation, placed: JsonObject, persona: str) -> None:
    """The same of a written call that was just opened, in a transaction of its own; the call ended if it cannot be."""

    async def keep() -> None:
        async with parts.sessions.begin() as session_:
            await keep_as_placed(session_, simulation, placed, persona)

    async with ending_what_never_began(parts, simulation, doing="keep how this call was placed"):
        await when_free(keep)


async def keep_cost(sessions: async_sessionmaker[AsyncSession], call: str, spending: Spending) -> None:
    """Add what the caller's lines and voice cost to the call's facts."""
    async with sessions.begin() as session_:
        await calls.add_caller_cost(session_, call, spending.usd)


async def keep_heard(
    sessions: async_sessionmaker[AsyncSession], store: Store, call: str, said: Sequence[hearing.Said]
) -> None:
    """Keep how the agent heard the call, against what its caller really said; nothing for a written one."""
    if not said:
        return
    heard = hearing.measure(await store.whole_of(call), said)
    async with sessions.begin() as session_:
        await calls.keep_caller_heard(session_, call, asdict(heard))


# What only the process that played the caller knows: whether its own loop was on time. A call whose
# line ran late was heard broken by its agent, and says nothing of the agent.
async def keep_line(sessions: async_sessionmaker[AsyncSession], call: str, pace: Mapping[str, float]) -> None:
    """Keep how the caller's leg kept to the clock with the call's facts."""
    async with sessions.begin() as session_:
        await calls.keep_caller_line(session_, call, pace)


# ── listed ──


@dataclass(frozen=True, slots=True)
class Scored:
    """What the judges said of a simulated call, as its list row carries it."""

    held: int
    judged: int
    passed: bool
    reason: str | None


@dataclass(frozen=True, slots=True)
class PlayedBy:
    """Who played the caller as it ran: `vendor/model` of its lines and of its voice, and the voice."""

    llm: str | None
    tts: str | None
    voice: str | None


@dataclass(frozen=True, slots=True)
class SimulatedCall:
    """One call a persona made: who played it, to whom, when, how it ended, what it cost."""

    call: str
    agent: str
    # Every simulated call names its persona; the facts' column is empty only for a person's call.
    persona: str | None
    started_at: float
    ended_at: float | None
    turns: int
    end_reason: str | None
    outcome: str | None
    cost_usd: float | None
    score: Scored | None
    # None for a call simulated before the runtime kept who played it.
    played_by: PlayedBy | None
    caller_cost_usd: float
    # What the agent ran on over its settings, and the comparison the call was placed in; None for a
    # call that ran the settings, placed on its own.
    against: Mapping[str, Any] | None
    comparison: str | None
    # How a spoken call was heard, against what its caller really said; None for a written one, and
    # until the simulation ends.
    hearing: Mapping[str, Any] | None


@dataclass(frozen=True, slots=True)
class SimulatedPage:
    """A page of simulated calls, newest first: one persona's, or the env's."""

    runs: list[SimulatedCall]
    total: int
    next: str | None


async def list_simulated(
    session_: AsyncSession, actor: Actor, wanted: calls.PersonaRunFilters, limit: int
) -> SimulatedPage:
    """The simulated calls the filter names in the key's env, in the copies it lists, newest first."""
    asked = replace(wanted, holders=calls.list_copies(actor))
    found = await calls.list_persona_runs(session_, actor.scope, asked, limit=limit)
    return SimulatedPage([_row_of(run) for run in found.runs], found.total, found.next)


async def list_of_persona(
    session_: AsyncSession, actor: Actor, agent: str, persona: str, *, before: str | None, limit: int
) -> SimulatedPage:
    """The calls the persona made to the agent in the key's env and scope, newest first."""
    declaration = await agents.declaration_of(session_, actor.scope, agent)
    class_personas = None if declaration is None else declaration.personas
    await judging.get_persona(session_, actor.org, agent, persona, class_personas)
    wanted = calls.PersonaRunFilters(agent=agent, persona=persona, before=before)
    return await list_simulated(session_, actor, wanted, limit)


def score_of(facts: folds.CallFacts) -> Scored | None:
    """What the judges said of the call, off its facts; None until it is scored."""
    if facts.judged is None or facts.passed is None:
        return None
    return Scored(held=facts.held or 0, judged=facts.judged, passed=facts.passed, reason=facts.reason)


def _row_of(run: calls.PersonaRun) -> SimulatedCall:
    facts, kept = folds.facts_of(run.facts), run.facts
    played_by = None if kept.caller_llm is None else PlayedBy(kept.caller_llm, kept.caller_tts, kept.caller_voice)
    return SimulatedCall(
        call=facts.call,
        agent=run.agent,
        persona=facts.persona,
        started_at=run.started_at,
        ended_at=facts.ended_at,
        turns=len(facts.heard_at),
        end_reason=facts.end_reason,
        outcome=facts.outcome,
        cost_usd=facts.cost_usd,
        score=score_of(facts),
        played_by=played_by,
        caller_cost_usd=kept.caller_cost_usd,
        against=kept.against,
        comparison=kept.comparison,
        hearing=kept.hearing,
    )
