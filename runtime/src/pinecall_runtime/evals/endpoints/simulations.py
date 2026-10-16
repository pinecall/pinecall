"""The simulation endpoints: a persona put on the agent, the caller's next line, a spoken call placed."""

from fastapi import APIRouter

from pinecall_runtime.accounts.service import keys
from pinecall_runtime.accounts.service.attempts import AttemptThrottle
from pinecall_runtime.calls import service as calls
from pinecall_runtime.calls.auth import TheServing
from pinecall_runtime.evals import schemas, service
from pinecall_runtime.evals.auth import EvalsKey, TheSimulations
from pinecall_runtime.exceptions import NotFound
from pinecall_runtime.judging import service as judging
from pinecall_runtime.kit.auth import Scope
from pinecall_runtime.postgres import Session
from pinecall_runtime.session import service as session_

router = APIRouter()

NOBODY_HOLDS = (
    "nobody holds {agent} in this env: a simulation calls the agent as a caller would, so a "
    "process must be answering it — deployed, or `pinecall start` in its directory"
)
# A caller's line is a model call: a call of forty turns says forty, and several run side by side.
LINES_A_MINUTE = 120
TOO_MANY_LINES = "more than 120 caller lines this minute from this org: try again in a minute"


# The gateway plays the caller, so the agent is called as anybody calls it: the process that
# holds it — deployed with `pinecall deploy`, on a server of the org's, or a developer's
# `pinecall start` — answers, and nothing about the agent changes for a simulation. What can be
# refused is refused before the answer: the persona, nobody holding the agent, the org's limits,
# a call id taken. The conversation is played after it, and watched as any call is.
@router.post("/v1/simulations")
async def simulate(
    body: schemas.SimulationRequest, actor: EvalsKey, serving: TheServing, simulations: TheSimulations, session: Session
) -> schemas.SimulationStarted:
    """Put one of the agent's personas on it, written or spoken; the call's id at once."""
    keys.check_agent(actor, body.agent)
    scope = actor.scope
    persona = await judging.persona_named(session, actor.org, body.agent, body.persona)
    if persona is None:
        raise NotFound(judging.NO_SUCH_PERSONA.format(name=body.persona, agent=body.agent))
    registration = serving.registry.serving(scope, body.agent, None)
    if registration is None:
        raise NotFound(NOBODY_HOLDS.format(agent=body.agent))
    await service.admit_simulation(session, serving, scope, body.agent)
    caller = service.calling_as(persona)
    line = service.line_of(caller.behavior, body.interferer_db, body.packet_loss, body.ambience)
    placed = service.Placed(calls.new_call_id(), body.agent, caller, body.turns, line, dict(persona.state))
    if body.voice:
        await service.claim_new_call(session, serving, placed.call, body.agent, scope)
        simulations.play(placed.call, _spoken(serving, scope, placed))
    else:
        running = await service.written_call(session, serving, registration, placed)
        simulations.play(placed.call, _written(serving, running, placed))
    return schemas.SimulationStarted(call=placed.call, voice=body.voice)


# The gateway holds the vendors' keys: the org's own when it brought one, else the box's lent.
@router.post("/v1/evals/caller")
async def next_line(
    body: schemas.NextLineRequest, actor: EvalsKey, serving: TheServing, session: Session
) -> schemas.NextLineResponse:
    """The persona's next line on the call so far, improvised by its model."""
    throttle = AttemptThrottle(serving.handles.sessions, LINES_A_MINUTE)
    await throttle.check(f"{actor.org} evals/caller", TOO_MANY_LINES)
    async with service.caller_model(session, serving, actor.scope, body.persona) as model:
        return (await service.improvise_line(model, body)).answer


# A persona is the agent's: a name nobody wrote for this agent is refused; one sent without a
# name is played as sent.
@router.post("/v1/evals/voice")
async def place_voice_call(
    body: schemas.PlaceVoiceCallRequest, actor: EvalsKey, serving: TheServing, session: Session
) -> schemas.PlaceVoiceCallResponse:
    """Dispatch the agent into a room, play the persona as a spoken caller, and hang up."""
    keys.check_agent(actor, body.agent)
    scope = actor.scope
    persona = body.persona
    if persona.name and await judging.get_persona(session, actor.org, body.agent, persona.name) is None:
        raise NotFound(judging.NO_SUCH_PERSONA.format(name=persona.name, agent=body.agent))
    await service.admit_simulation(session, serving, scope, body.agent)
    await service.claim_new_call(session, serving, body.call, body.agent, scope)
    line = service.line_of(persona.behavior, body.interferer_db, body.packet_loss, body.ambience)
    placed = service.Placed(body.call, body.agent, persona, body.turns, line, dict(body.state))
    turns, spending = await service.spoken_call(session, serving, scope, placed)
    return schemas.PlaceVoiceCallResponse(
        call=body.call,
        turns=turns,
        line=service.described(line),
        caller_cost_usd=spending.usd,
        stopped_at_ceiling=spending.is_over,
    )


# Played after the endpoint answered, on sessions of their own: the request's is closed by then.
async def _spoken(serving: calls.Serving, scope: Scope, placed: service.Placed) -> None:
    async with serving.handles.sessions.begin() as session:
        await service.spoken_call(session, serving, scope, placed)


async def _written(serving: calls.Serving, running: session_.Session, placed: service.Placed) -> None:
    async with serving.handles.sessions.begin() as session:
        await service.written_turns(session, serving, running, placed)
