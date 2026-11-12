"""The simulation endpoints: a persona put on the agent, the simulated calls listed, a caller's line, a spoken call."""

from dataclasses import asdict
from typing import Annotated, Any

from fastapi import APIRouter, Query

from runtime.actor import Actor
from runtime.agents import service as agents
from runtime.agents.auth import KnownAgent
from runtime.calls import service as calls
from runtime.enums import KeyScope
from runtime.evals import schemas
from runtime.evals.auth import EvalsKey, TheHarness
from runtime.evals.service import personas, simulated_calls, simulations
from runtime.evals.service.callers import Heard
from runtime.exceptions import Forbidden
from runtime.judging import service as judging
from runtime.kit.text import JsonObject
from runtime.postgres import Session

router = APIRouter()

A_PIPELINE_KEY = "a key that opens `pipeline` runs the agent on another voice or model for a simulation"


# What can be refused is refused before the answer; the conversation is played after it, and watched
# as any call is. A spoken one with no slot free waits for the fleet to grow, `fleet.full` on the
# agent's log meanwhile.
@router.post("/v1/simulations")
async def simulate(body: schemas.SimulationRequest, actor: EvalsKey, parts: TheHarness) -> schemas.SimulationStarted:
    """Put one of the agent's personas on it, written or spoken; the call's id at once."""
    against = check_agent_values(actor, body.against)
    started = await simulations.place_simulation(parts, actor, simulation_of(body), against=against, comparison=None)
    return schemas.SimulationStarted(call=started.call, voice=started.spoken)


@router.get("/v1/simulations")
async def list_simulations(
    actor: EvalsKey, session: Session, query: Annotated[schemas.SimulationQuery, Query()]
) -> schemas.PersonaRunList:
    """Every simulated call in the key's env and scope, or the agents named's, newest first."""
    wanted = calls.PersonaRunFilters(
        agents=tuple(query.agent), before=query.before, call=query.call, comparison=query.comparison
    )
    return schemas.PersonaRunList.of(await simulated_calls.list_simulated(session, actor, wanted, query.limit))


@router.get("/v1/simulations/limits")
async def simulation_limits(actor: EvalsKey, parts: TheHarness, session: Session) -> schemas.SimulationLimits:
    """How the key's org may shape its simulations in the env: the calls at once, and the calls a comparison places."""
    return schemas.SimulationLimits.of(await simulations.limits_of(session, parts, actor))


@router.get("/v1/agents/{slug}/personas/{name}/runs")
async def list_persona_runs(
    slug: KnownAgent, name: str, actor: EvalsKey, session: Session, query: Annotated[schemas.PersonaRunQuery, Query()]
) -> schemas.PersonaRunList:
    """The calls the persona made to the agent in the key's env and scope, newest first."""
    found = await simulated_calls.list_of_persona(session, actor, slug, name, before=query.before, limit=query.limit)
    return schemas.PersonaRunList.of(found)


@router.post("/v1/agents/{slug}/personas/{name}/brief")
async def brief_persona(slug: KnownAgent, name: str, actor: EvalsKey, parts: TheHarness) -> schemas.CallerPersona:
    """The persona as a simulation plays it: Pinecall's briefed on this agent (one eval), the agent's own as written."""
    return caller_of(await personas.brief_for(parts, actor, slug, name))


@router.post("/v1/evals/caller")
async def next_line(body: schemas.NextLineRequest, actor: EvalsKey, parts: TheHarness) -> schemas.NextLineResponse:
    """The persona's next line on the call so far, improvised by its model."""
    heard = [Heard(turn.who, turn.said) for turn in body.heard]
    line = await simulations.improvise_next_line(parts, actor, persona_of(body.persona), heard, body.turns_left)
    return schemas.NextLineResponse(say=line.say, hangup=line.hangup)


# The request is held for the whole call and answered when the caller has hung up: the CLI's way.
@router.post("/v1/evals/voice")
async def place_voice_call(
    body: schemas.PlaceVoiceCallRequest, actor: EvalsKey, parts: TheHarness
) -> schemas.PlaceVoiceCallResponse:
    """Dispatch the agent into a room, play the persona as a spoken caller, and hang up."""
    asked = simulations.VoiceCall(
        call=body.call,
        agent=body.agent,
        persona=persona_of(body.persona),
        turns=body.turns,
        interferer_db=body.interferer_db,
        packet_loss=body.packet_loss,
        ambience=body.ambience,
        pause_s=body.pause_s,
        state=body.state,
    )
    return schemas.PlaceVoiceCallResponse.of(await simulations.place_voice_call(parts, actor, asked))


# A test room's rule: the sandbox's alone, only those values, and a key that edits the pipeline.
def check_agent_values(actor: Actor, against: schemas.AgentValues | None) -> JsonObject:
    """The voice and models a run puts the agent on, checked as a test room's are; none said is none."""
    named: dict[str, Any] = {} if against is None else against.model_dump(exclude_none=True)
    if not named:
        return {}
    if KeyScope.pipeline not in actor.scopes:
        raise Forbidden(A_PIPELINE_KEY)
    return agents.check_test_values(named, env=actor.env)


def simulation_of(body: schemas.SimulationWants) -> simulations.Wanted:
    """A simulation as its body asks for it."""
    played, scenario = body.played_by, body.scenario
    return simulations.Wanted(
        agent=body.agent,
        persona=body.persona,
        spoken=body.voice,
        turns=body.turns,
        interferer_db=body.interferer_db,
        packet_loss=body.packet_loss,
        ambience=body.ambience,
        pause_s=body.pause_s,
        played_by=None if played is None else judging.Played(**played.model_dump()),
        scenario=None if scenario is None else simulations.Scenario(scenario.goal, scenario.facts),
    )


def persona_of(body: schemas.CallerPersona) -> judging.Persona:
    """The caller a body names, as the harness plays it."""
    return judging.Persona(
        name=body.name,
        goal=body.goal,
        style=body.style,
        facts={name: str(value) for name, value in body.facts.items()},
        llm=body.llm,
        tts=body.tts,
        voice=body.voice,
        expects=tuple(body.expects),
        behavior=judging.Behavior(**body.behavior.model_dump()),
    )


def caller_of(persona: judging.Persona) -> schemas.CallerPersona:
    """A persona as the caller endpoints answer it."""
    return schemas.CallerPersona.model_validate(
        {
            "name": persona.name,
            "goal": persona.goal,
            "style": persona.style,
            "facts": dict(persona.facts),
            "llm": persona.llm,
            "tts": persona.tts,
            "voice": persona.voice,
            "expects": list(persona.expects),
            "behavior": asdict(persona.behavior),
        }
    )
