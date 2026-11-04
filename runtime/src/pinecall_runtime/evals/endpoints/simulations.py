"""The simulation endpoints: a persona put on the agent, the caller's next line, a spoken call placed."""

from typing import Any

from fastapi import APIRouter

from pinecall_runtime.accounts.service import keys
from pinecall_runtime.accounts.service.attempts import AttemptThrottle
from pinecall_runtime.agents.service import registry, settings
from pinecall_runtime.calls import service as calls
from pinecall_runtime.calls.auth import TheServing
from pinecall_runtime.enums import KeyScope
from pinecall_runtime.evals import schemas, service
from pinecall_runtime.evals.auth import EvalsKey, TheSimulations
from pinecall_runtime.evals.endpoints.reading import declared_personas_of
from pinecall_runtime.exceptions import Forbidden, NotFound, PinecallError
from pinecall_runtime.judging import service as judging
from pinecall_runtime.kit.auth import Actor, Scope
from pinecall_runtime.kit.crypto import random_id
from pinecall_runtime.kit.text import JsonObject
from pinecall_runtime.postgres import Session
from pinecall_runtime.providers import service as providers
from pinecall_runtime.session import service as session_

router = APIRouter()

# A caller's line is a model call: a call of forty turns says forty, and several run side by side.
LINES_A_MINUTE = 120
TOO_MANY_LINES = "more than 120 caller lines this minute from this org: try again in a minute"
A_PIPELINE_KEY = "a key that opens `pipeline` runs the agent on another voice or model for a simulation"


# The gateway plays the caller, so the agent is called as anybody calls it: the process that
# holds it — deployed with `pinecall deploy`, on a server of the org's, or a developer's
# `pinecall start` — answers, and nothing about the agent changes for a simulation. What can be
# refused is refused before the answer: the persona, nobody holding the agent, the org's limits,
# the calls already on the line, a call id taken. The conversation is played after it, and
# watched as any call is; a spoken one with no seat free waits for the fleet to grow (a scaled
# worker's node takes a minute or two), `fleet.full` on the agent's log meanwhile.
@router.post("/v1/simulations")
async def simulate(
    body: schemas.SimulationRequest, actor: EvalsKey, serving: TheServing, simulations: TheSimulations, session: Session
) -> schemas.SimulationStarted:
    """Put one of the agent's personas on it, written or spoken; the call's id at once."""
    against = _agent_values(actor, body.against)
    return await _placed(session, serving, simulations, actor, body, against=against, comparison=None)


# Each call is placed as `POST /v1/simulations` places one, under one id they share; one refused
# (a vendor nobody keyed, the org's limits) is said beside the ones that started, which go on.
@router.post("/v1/simulations/compare")
async def compare(
    body: schemas.ComparisonRequest, actor: EvalsKey, serving: TheServing, simulations: TheSimulations, session: Session
) -> schemas.ComparisonStarted:
    """One persona against the agent under each voice and models named, placed together; what started and what not."""
    comparison = random_id(service.COMPARISON_PREFIX, 6)
    started: list[schemas.ComparedCall] = []
    refused: list[schemas.ComparedRefusal] = []
    for values in body.against:
        against = _agent_values(actor, values)
        try:
            placed = await _placed(session, serving, simulations, actor, body, against=against, comparison=comparison)
        except PinecallError as why:
            refused.append(schemas.ComparedRefusal(against=against, why=str(why)))
            continue
        started.append(schemas.ComparedCall(against=against, call=placed.call))
    return schemas.ComparisonStarted(comparison=comparison, voice=body.voice, calls=started, refused=refused)


@router.get("/v1/simulations/compare/{comparison}")
async def read_comparison(
    comparison: str, actor: EvalsKey, serving: TheServing, session: Session
) -> schemas.Comparison:
    """The comparison's calls, best first: every judge held, then the fastest reply, then the cheapest."""
    wanted = calls.PersonaRunFilters(comparison=comparison)
    found = await calls.runs_of_persona(session, actor.scope, wanted, limit=service.COMPARED_AT_MOST)
    if not found.runs:
        raise NotFound(service.NO_SUCH_COMPARISON.format(comparison=comparison))
    rows = [await service.compared_row(serving, run) for run in found.runs]
    first = calls.facts_of(found.runs[0].facts)
    return schemas.Comparison(
        comparison=comparison,
        agent=found.runs[0].agent,
        persona=first.persona or "",
        voice=first.spoken,
        rows=service.ranked(rows),
    )


# A test room's rule: the sandbox's alone, only those knobs, and a key that edits the pipeline.
def _agent_values(actor: Actor, against: schemas.AgentValues | None) -> JsonObject:
    named: dict[str, Any] = {} if against is None else against.named()
    if not named:
        return {}
    if KeyScope.pipeline not in actor.scopes:
        raise Forbidden(A_PIPELINE_KEY)
    return settings.check_test_values(named, env=actor.env)


async def _placed(
    session: Session,
    serving: calls.Serving,
    simulations: service.Simulations,
    actor: Actor,
    body: schemas.SimulationWants,
    *,
    against: JsonObject,
    comparison: str | None,
) -> schemas.SimulationStarted:
    keys.check_agent(actor, body.agent)
    scope = actor.scope
    roster = await declared_personas_of(session, serving, scope, body.agent)
    persona = await judging.persona_named(session, actor.org, body.agent, body.persona, roster)
    if persona is None:
        raise NotFound(judging.NO_SUCH_PERSONA.format(name=body.persona, agent=body.agent))
    if body.played_by is not None:
        persona = await service.played_on(session, persona, body.played_by)
    registration = serving.registry.serving(scope, body.agent, None)
    if registration is None:
        raise registry.NoApp(body.agent)
    call = calls.new_call_id()
    caller = service.calling_as(persona)
    # The place on the line is taken before anything is awaited, and given back if what follows
    # refuses the call: a burst of requests can never all pass the count together.
    simulations.admit(call, scope)
    try:
        await service.admit_simulation(session, serving, scope, body.agent, caller, voice=body.voice, waits=True)
        line = service.line_of(caller.behavior, body.interferer_db, body.packet_loss, body.ambience)
        placed = service.Placed(
            call,
            body.agent,
            caller,
            body.turns,
            line,
            dict(persona.state),
            waits_for_seat=body.voice,
            against=against,
            comparison=comparison,
        )
        if body.voice:
            await service.claim_new_call(session, serving, placed.call, body.agent, scope)
            simulations.play(placed.call, scope, _spoken(serving, scope, placed))
        else:
            running = await service.written_call(session, serving, registration, placed)
            simulations.play(placed.call, scope, _written(serving, running, placed))
    except BaseException:
        simulations.release(call)
        raise
    return schemas.SimulationStarted(call=placed.call, voice=body.voice)


# The gateway holds the vendors' keys: the org's own when it brought one, else the box's lent.
@router.post("/v1/evals/caller")
async def next_line(body: schemas.NextLineRequest, actor: EvalsKey, serving: TheServing) -> schemas.NextLineResponse:
    """The persona's next line on the call so far, improvised by its model."""
    throttle = AttemptThrottle(serving.handles.sessions, LINES_A_MINUTE)
    await throttle.check(f"{actor.org} evals/caller", TOO_MANY_LINES)
    async with service.caller_model(serving, actor.scope, body.persona) as model:
        return (await service.improvise_line(model.llm, body)).answer


# A persona is the agent's own or Pinecall's library's, as the written simulation takes it: a name
# that is neither is refused; one sent without a name is played as sent.
@router.post("/v1/evals/voice")
async def place_voice_call(
    body: schemas.PlaceVoiceCallRequest,
    actor: EvalsKey,
    serving: TheServing,
    simulations: TheSimulations,
    session: Session,
) -> schemas.PlaceVoiceCallResponse:
    """Dispatch the agent into a room, play the persona as a spoken caller, and hang up."""
    keys.check_agent(actor, body.agent)
    scope = actor.scope
    persona = body.persona
    roster = await declared_personas_of(session, serving, scope, body.agent)
    if persona.name and await judging.persona_named(session, actor.org, body.agent, persona.name, roster) is None:
        raise NotFound(judging.NO_SUCH_PERSONA.format(name=persona.name, agent=body.agent))
    judging.check_persona_models(await providers.get_catalog(session), persona.llm, persona.tts, persona.voice)
    # A ring with nobody to answer it would wait forty seconds for an agent that never joins.
    if serving.registry.serving(scope, body.agent, None) is None:
        raise registry.NoApp(body.agent)
    async with simulations.admitted(body.call, scope):
        await service.admit_simulation(session, serving, scope, body.agent, persona, voice=True)
        await service.claim_new_call(session, serving, body.call, body.agent, scope)
        line = service.line_of(persona.behavior, body.interferer_db, body.packet_loss, body.ambience)
        placed = service.Placed(body.call, body.agent, persona, body.turns, line, dict(body.state))
        # The request's writes are done: the call is played with no connection of the pool held for it.
        await session.commit()
        turns, spending = await service.spoken_call(serving, scope, placed)
    return schemas.PlaceVoiceCallResponse(
        call=body.call,
        turns=turns,
        line=service.described(line),
        caller_cost_usd=spending.usd,
        stopped_at_ceiling=spending.is_over,
    )


# Played after the endpoint answered: the request's session is closed by then, and a call holds none.
async def _spoken(serving: calls.Serving, scope: Scope, placed: service.Placed) -> None:
    await service.spoken_call(serving, scope, placed)


async def _written(serving: calls.Serving, running: session_.Session, placed: service.Placed) -> None:
    await service.written_turns(serving, running, placed)
