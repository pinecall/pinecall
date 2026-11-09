"""The simulation endpoints: a persona put on the agent, the caller's next line, a spoken call placed."""

from collections.abc import Awaitable, Callable
from typing import Any

from fastapi import APIRouter

from pinecall_runtime.accounts.service import keys
from pinecall_runtime.accounts.service.attempts import AttemptThrottle
from pinecall_runtime.agents.service import registry, settings
from pinecall_runtime.billing import service as billing
from pinecall_runtime.calls import service as calls
from pinecall_runtime.calls.auth import TheServing
from pinecall_runtime.enums import KeyScope
from pinecall_runtime.evals import schemas, service
from pinecall_runtime.evals.auth import EvalsKey, TheSimulations
from pinecall_runtime.evals.endpoints.reading import declared_personas_of
from pinecall_runtime.exceptions import Forbidden, NotFound, PinecallError, ValidationError
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


# Each call is placed as `POST /v1/simulations` places one, under one id they share: every caller
# against every configuration, as many times as asked. The ones the org's line has room for are
# placed before the answer; the rest wait their turn and are placed by this gateway as the ones
# before them end, the comparison's row saying how many still wait. One refused (a vendor nobody
# keyed, the org's limits) is said beside the ones that started, which go on.
@router.post("/v1/simulations/compare")
async def compare(
    body: schemas.ComparisonRequest, actor: EvalsKey, serving: TheServing, simulations: TheSimulations, session: Session
) -> schemas.ComparisonStarted:
    """Each persona against the agent under each voice and models named, as many times as asked; what started."""
    personas = body.personas
    quotas = await billing.get_quotas(session, actor.org, actor.env)
    asked = len(personas) * len(body.against) * body.repeats
    if asked > quotas.compared_at_most:
        said = service.TOO_MANY_COMPARED.format(
            most=quotas.compared_at_most,
            personas=len(personas),
            configs=len(body.against),
            repeats=body.repeats,
            calls=asked,
        )
        raise ValidationError(said)
    # Every configuration is checked before anything is placed: one the key may not name refuses the whole.
    against = [_agent_values(actor, values) for values in body.against]
    plan = service.Plan(
        comparison=random_id(service.COMPARISON_PREFIX, 6),
        agent=body.agent,
        scope=actor.scope,
        voice=body.voice,
        personas=personas,
        against=[dict(values) for values in against],
        repeats=body.repeats,
        started_at=serving.logs.store.clock(),
    )
    wants = body.model_dump(exclude={"against", "more_personas", "repeats"})

    async def place(pair: service.Pair, within: Session) -> schemas.SimulationStarted:
        one = schemas.SimulationWants.model_validate({**wants, "persona": pair.persona})
        return await _placed(
            within, serving, simulations, actor, one, against=dict(pair.against), comparison=plan.comparison
        )

    started: list[schemas.ComparedCall] = []
    waiting: list[service.Pair] = []
    for pair in plan.pairs():
        # Once one waits for a place, every one after it waits behind it: the order asked for is kept.
        if waiting:
            waiting.append(pair)
            continue
        try:
            placed = await place(pair, session)
        except service.TooManyAtOnce:
            waiting.append(pair)
            continue
        except PinecallError as why:
            plan.refused.append(schemas.ComparedRefusal(persona=pair.persona, against=pair.against, why=str(why)))
            continue
        started.append(schemas.ComparedCall(persona=pair.persona, against=pair.against, call=placed.call))
    plan.waiting = len(waiting)
    plan.heard_at = serving.logs.store.clock()
    await service.keep_plan(session, plan)
    if waiting:
        simulations.place_later(_placed_in_turn(serving, plan, waiting, place))
    return schemas.ComparisonStarted(
        comparison=plan.comparison, voice=body.voice, calls=started, refused=plan.refused, waiting=len(waiting)
    )


# Played after the endpoint answered: each call is placed in a transaction of its own, and the plan's
# row is rewritten as each one is, so the board reads how many still wait from any gateway.
async def _placed_in_turn(
    serving: calls.Serving,
    plan: service.Plan,
    waiting: list[service.Pair],
    place: Callable[[service.Pair, Session], Awaitable[schemas.SimulationStarted]],
) -> None:
    async def placed(pair: service.Pair) -> None:
        async with serving.handles.sessions.begin() as within:
            await place(pair, within)

    async def said() -> None:
        async with serving.handles.sessions.begin() as within:
            await service.keep_plan(within, plan)

    await service.place_waiting(plan, waiting, placed, said, clock=serving.logs.store.clock)


@router.get("/v1/simulations/compare/{comparison}")
async def read_comparison(
    comparison: str, actor: EvalsKey, serving: TheServing, session: Session
) -> schemas.Comparison:
    """The comparison's calls, each caller's best first: its goal held, every judge, the fastest, the cheapest."""
    wanted = calls.PersonaRunFilters(comparison=comparison, holders=calls.copies_listed(actor))
    found = await calls.runs_of_persona(session, actor.scope, wanted, limit=service.ROWS_READ_AT_MOST)
    plan = await service.plan_of(session, actor.scope, comparison)
    if not found.runs and plan is None:
        raise NotFound(service.NO_SUCH_COMPARISON.format(comparison=comparison))
    rows = [await service.compared_row(serving, run) for run in found.runs]
    # What was asked for names the callers before any of them has a call; one made before plans were
    # kept is what its calls say.
    personas = service.in_the_order_placed(rows) if plan is None else plan.personas
    spoken = calls.facts_of(found.runs[0].facts).spoken if plan is None else plan.voice
    return schemas.Comparison(
        comparison=comparison,
        agent=found.runs[0].agent if plan is None else plan.agent,
        persona=personas[0],
        personas=personas,
        voice=spoken,
        rows=service.ranked(rows),
        against=[] if plan is None else plan.against,
        repeats=1 if plan is None else plan.repeats,
        planned=len(rows) if plan is None else plan.planned,
        waiting=0 if plan is None else plan.waiting,
        refused=[] if plan is None else plan.refused,
        abandoned=plan is not None and service.was_left(plan, serving.logs.store.clock()),
    )


@router.get("/v1/simulations/limits")
async def simulation_limits(actor: EvalsKey, simulations: TheSimulations, session: Session) -> schemas.SimulationLimits:
    """How the key's org may shape its simulations in the env: the calls at once, and the calls a comparison places."""
    quotas = await billing.get_quotas(session, actor.org, actor.env)
    return schemas.SimulationLimits(
        at_once=quotas.simulating_at_most,
        on_the_line=simulations.on_the_line(actor.org, actor.env),
        comparison_calls=quotas.compared_at_most,
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
    # The caller phones about what the body says; else a caller of the library is briefed on this agent
    # before it phones: what it calls about, in the agent's terms.
    caller = service.calling_as(persona)
    if body.scenario is not None:
        caller = service.as_scenario(caller, body.scenario.goal, body.scenario.facts)
    else:
        caller = await service.briefed(session, serving, scope, body.agent, caller)
    # The place on the line is taken before anything is awaited, and given back if what follows
    # refuses the call: a burst of requests can never all pass the count together.
    quotas = await billing.get_quotas(session, scope.org, scope.env)
    simulations.admit(call, scope, quotas.simulating_at_most)
    try:
        await service.admit_simulation(session, serving, scope, body.agent, caller, voice=body.voice, waits=True)
        line = service.line_of(
            caller.behavior, body.interferer_db, body.packet_loss, body.ambience, pause_s=body.pause_s
        )
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
            running = await service.written_call(session, serving, calls.written_for(registration, scope), placed)
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
    quotas = await billing.get_quotas(session, scope.org, scope.env)
    async with simulations.admitted(body.call, scope, quotas.simulating_at_most):
        await service.admit_simulation(session, serving, scope, body.agent, persona, voice=True)
        await service.claim_new_call(session, serving, body.call, body.agent, scope)
        line = service.line_of(
            persona.behavior, body.interferer_db, body.packet_loss, body.ambience, pause_s=body.pause_s
        )
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
