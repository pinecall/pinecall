"""A simulated call: played on its line by a caller of its own, what that cost and how it was heard kept with it."""

import logging
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass, field, replace
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from runtime.actor import Actor, Scope
from runtime.agents import service as agents
from runtime.agents.declaration import Declaration
from runtime.calls import folds
from runtime.calls import service as calls
from runtime.compliance import service as compliance
from runtime.evals.parts import Harness
from runtime.evals.service import hearing, lines
from runtime.evals.service.callers import (
    Caller,
    Spending,
    caller_voice,
    improvise_line,
    list_heard,
    name_of,
    open_caller_model,
)
from runtime.evals.service.leg import Spoken
from runtime.evals.service.spoken import SpokenLine
from runtime.evals.service.turns import NextLine, is_call_over
from runtime.evals.service.written import WrittenLine
from runtime.judging import service as judging
from runtime.kit.text import Json, JsonObject
from runtime.providers import service as providers
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


@dataclass(frozen=True, slots=True)
class Played:
    """A simulated call played to its end: the lines its caller said, and what they cost."""

    turns: int
    spending: Spending


# The agent is dispatched into a room whoever holds it, and the caller speaks there in a voice of its own.
async def play_spoken(parts: Harness, simulation: Simulation) -> Played:
    """Play the persona out loud on the agent's line; the lines said, and what they cost."""
    scope, persona = simulation.scope, simulation.persona
    dispatch = Dispatch(
        agent=simulation.agent,
        org=scope.org,
        env=scope.env,
        holder=scope.holder or None,
        caller=A_SIMULATED_CALLER,
        persona=persona.name or None,
        expects=list(persona.expects),
        state=dict(simulation.state),
        tuning=dict(simulation.against),
    )
    async with parts.sessions.begin() as session_:
        voice = await caller_voice(
            session_, parts.vault, scope, await agent_as_it_runs(session_, parts, scope, simulation.agent), persona
        )
        notice = await opens_with_a_notice(session_, scope, voice.language)
    await keep_against(parts, simulation)
    # The caller murmurs in the language it speaks: the line learns it here, with the voice.
    spoken = Spoken(simulation.call, simulation.acts, language=voice.language, notice=notice)
    line = SpokenLine(parts, dispatch, voice, spoken, waits_for_slot=simulation.waits_for_slot)
    return await play(parts, simulation, line, voice)


async def play_written(parts: Harness, running: session.Session, simulation: Simulation) -> Played:
    """The persona's lines said on the written call, until it hangs up; and what they cost."""
    return await play(parts, simulation, WrittenLine(running, parts.logs, parts.store), None)


# The one skeleton of a simulated call, whatever line it is on. Until 2026-11 it was written twice, a
# spoken and a written one, and a third time for a golden said out loud, which forgot what the caller
# spent and how it was heard. What was spent is kept whatever ended the call, a caller hanging up or
# the line failing: it was spent. Only a simulation knows what its caller really said and when: how the
# agent heard it is measured against that once the caller has left, and kept with the call's facts.
async def play(parts: Harness, simulation: Simulation, line: lines.Line, voice: Running | None) -> Played:
    """Play the simulation on its line: who plays it kept as it starts, its lines said, its cost and hearing kept."""
    async with parts.sessions.begin() as session_:
        spending = Spending(await providers.get_catalog(session_))
    async with open_caller_model(parts.sessions, parts.vault, simulation.scope, simulation.persona) as model:
        caller = Caller(simulation.persona, model.model, spending)
        await _keep_played_by(parts, simulation.call, model.named, voice)
        try:
            turns = await lines.play(line, simulation.turns, improvise(parts, simulation.call, caller), spending.count)
        finally:
            await keep_cost(parts, simulation.call, spending)
            await keep_heard(parts, simulation.call, line.list_said())
    return Played(turns, spending)


# Asked before each line: the line that crosses the ceiling is the last one said, and a call the
# agent or a person already ended asks for none.
def improvise(parts: Harness, call: str, caller: Caller) -> NextLine:
    """The caller's next line on the call so far, and whether it hangs up after it."""

    async def next_line(turns_left: int) -> tuple[str, bool]:
        entries = await parts.store.whole_of(call)
        if is_call_over(entries) or caller.spending.is_over:
            return "", True
        line = await improvise_line(caller.model, caller.persona, list_heard(entries), turns_left)
        caller.spending.count(line.usage)
        return line.say, line.hangup

    return next_line


# The agent as a call of the scope runs it, where an app of the org holds it: what the caller's voice is
# picked against (its language, the voice it speaks in).
async def agent_as_it_runs(session_: AsyncSession, parts: Harness, scope: Scope, agent: str) -> Declaration | None:
    """The agent's declaration over the settings of whoever holds it; None when no app of the org does."""
    held = parts.apps.find(scope, agent)
    if held is None or held.scope.org != scope.org:
        return None
    catalog = await providers.get_catalog(session_)
    of_its_class = (await agents.agent_of(session_, held.scope, agent)).whole
    return (await agents.resolve_for_call(session_, of_its_class, held.scope, catalog)).declaration


# The agent says the org's recording notice before its greeting: a caller that did not expect it would
# take it for the opening and talk over the greeting.
async def opens_with_a_notice(session_: AsyncSession, scope: Scope, language: str | None) -> bool:
    """Whether a spoken call of this org opens with a recording notice."""
    return (await compliance.policy_of(session_, scope.org)).notice_in(language) is not None


# Kept as the call starts, so the call's page names who plays the caller while it plays.
async def _keep_played_by(parts: Harness, call: str, model: str, voice: Running | None) -> None:
    tts, chosen = (None, None) if voice is None else (name_of(voice), voice.voice)
    async with parts.sessions.begin() as session_:
        await calls.keep_caller_played(session_, call, llm=model, tts=tts, voice=chosen)


async def keep_against(parts: Harness, simulation: Simulation) -> None:
    """Keep what the agent runs on for this call alone, its comparison and its caller, with the call's facts."""
    if not simulation.against and simulation.comparison is None:
        return
    async with parts.sessions.begin() as session_:
        await calls.keep_agent_values(
            session_,
            simulation.call,
            against=simulation.against or None,
            comparison=simulation.comparison,
            persona=simulation.persona.name,
        )


async def keep_cost(parts: Harness, call: str, spending: Spending) -> None:
    """Add what the caller's lines and voice cost to the call's facts."""
    async with parts.sessions.begin() as session_:
        await calls.add_caller_cost(session_, call, spending.usd)


async def keep_heard(parts: Harness, call: str, said: Sequence[hearing.Said]) -> None:
    """Keep how the agent heard the call, against what its caller really said; nothing for a written one."""
    if not said:
        return
    heard = hearing.measure(await parts.store.whole_of(call), said)
    async with parts.sessions.begin() as session_:
        await calls.keep_caller_heard(session_, call, asdict(heard))


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
