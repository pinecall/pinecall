"""The persona endpoints: Pinecall's switched, an agent's own, what each ran, and the org's at once."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query

from pinecall_runtime.agents.auth import KnownAgent
from pinecall_runtime.billing import service as billing
from pinecall_runtime.calls import service as calls
from pinecall_runtime.calls.auth import Reader, TheServing, reading
from pinecall_runtime.enums import KeyScope
from pinecall_runtime.evals import schemas
from pinecall_runtime.evals.auth import EvalsKey
from pinecall_runtime.evals.endpoints.reading import asked_by, readable
from pinecall_runtime.exceptions import Conflict, Forbidden, NotFound, ServiceUnavailable
from pinecall_runtime.judging import schemas as judged
from pinecall_runtime.judging import service as judging
from pinecall_runtime.kit.auth import Actor, Scope
from pinecall_runtime.kit.time import epoch
from pinecall_runtime.postgres import Session
from pinecall_runtime.providers import service as providers

router = APIRouter()

EvalsReader = Annotated[Reader, Depends(reading(KeyScope.evals))]

A_KEY_LISTS = "a list of simulated calls is read with a key, not a call's token"


# Every agent's callers, the org's roster at once: one list for both envs, as an agent's is.
@router.get("/v1/personas")
async def list_every_persona(actor: EvalsKey, session: Session) -> judged.PersonaList:
    """Every agent's callers, by agent and then by name."""
    kept = await judging.every_persona(session, actor.org)
    return judged.PersonaList(personas=[judging.persona_row(stored) for stored in kept])


# Every simulated call of the key's env and scope, whichever persona: the agents named's
# (`?agent=` once or more), or — none named — every agent's.
@router.get("/v1/simulations")
async def list_simulations(
    reader: EvalsReader, session: Session, query: Annotated[schemas.SimulationQuery, Query()]
) -> schemas.PersonaRunList:
    """Every simulated call in the key's env and scope, or the agents named's, newest first."""
    wanted = calls.PersonaRunFilters(agents=tuple(query.agent), before=query.before, call=query.call)
    return await _runs(session, reader, wanted, query.limit)


# One list for both envs: a persona is test data, never heard by a customer.
@router.get("/v1/agents/{slug}/personas")
async def list_personas(slug: KnownAgent, actor: EvalsKey, session: Session) -> judged.PersonaList:
    """Pinecall's personas as switched for the agent, then the agent's own, by name."""
    return judged.PersonaList(personas=await judging.list_personas(session, actor.org, slug))


# Written on the model the agent's calls are judged on: one eval a persona written, none on the
# org's own key. Nothing is saved; a person keeps the ones worth keeping with PUT.
@router.post("/v1/agents/{slug}/personas/generate")
async def generate_personas(
    slug: KnownAgent, body: judged.GeneratePersonas, actor: EvalsKey, serving: TheServing, session: Session
) -> judged.GeneratedPersonas:
    """Callers written for the agent from its prompt, tools, knowledge, a call or a template."""
    scope = actor.scope
    registration = serving.registry.serving(scope, slug, None)
    declared = None if registration is None else registration.config
    configured = await providers.get_catalog(session)
    judge = await calls.judge_of(session, serving, configured, scope, declared)
    if judge.running is None:
        raise ServiceUnavailable(judge.unjudged)
    if judge.running.lent:
        await billing.admit_evals(session, scope.org, scope.env, at=epoch())
    brief = await _brief_of(session, serving, actor, slug, body)
    model = providers.llm_of(judge.running)
    try:
        proposed, usage = await judging.write_personas(model, brief, body.n)
    finally:
        await model.aclose()
    named = (body.from_call,) if body.from_call else ()
    run = judging.JudgeRun("generate", "personas", scope.env, evals=len(proposed), calls=named)
    spent = judging.judge_spend(run, judge.running, configured, usage)
    await serving.logs.agent(slug).append("evals.spent", spent.dump())
    return judged.GeneratedPersonas(
        personas=[judging.proposed_row(persona) for persona in proposed],
        evals=spent.evals,
        cost_usd=spent.judge_cost_usd or 0.0,
    )


# A model or a vendor this box lacks is refused when written, not on the call that plays it.
@router.put("/v1/agents/{slug}/personas/{name}")
async def put_persona(
    slug: KnownAgent, name: str, body: judged.PersonaRequest, actor: EvalsKey, session: Session
) -> judged.PersonaList:
    """Write one of the agent's callers whole, or rename one from `was`; or switch Pinecall's."""
    judging.check_persona_models(await providers.get_catalog(session), body.llm, body.tts, body.voice)
    if name in judging.library_personas():
        await judging.write_library_persona(session, actor.org, slug, name, body, by=asked_by(actor))
    else:
        if body.on is not None:
            raise Conflict(judging.NOT_A_PERSONA_SWITCH.format(name=name))
        persona = judging.persona_of(name, body)
        await judging.put_persona(session, actor.org, slug, persona, by=asked_by(actor), was=body.was)
    return judged.PersonaList(personas=await judging.list_personas(session, actor.org, slug))


@router.delete("/v1/agents/{slug}/personas/{name}")
async def delete_persona(slug: KnownAgent, name: str, actor: EvalsKey, session: Session) -> judged.PersonaList:
    """Forget one of the agent's callers; 404 for a name nobody wrote, 409 for Pinecall's."""
    await judging.delete_persona(session, actor.org, slug, name)
    return judged.PersonaList(personas=await judging.list_personas(session, actor.org, slug))


# A name nobody wrote for the agent is a 404, not an empty page.
@router.get("/v1/agents/{slug}/personas/{name}/runs")
async def list_persona_runs(
    slug: KnownAgent,
    name: str,
    reader: EvalsReader,
    session: Session,
    query: Annotated[schemas.PersonaRunQuery, Query()],
) -> schemas.PersonaRunList:
    """The calls the persona made to the agent in the key's env and scope, newest first."""
    scope = reader.scope
    if reader.actor is None or scope is None:
        raise Forbidden(A_KEY_LISTS)
    if await judging.persona_named(session, scope.org, slug, name) is None:
        raise NotFound(judging.NO_SUCH_PERSONA.format(name=name, agent=slug))
    wanted = calls.PersonaRunFilters(agent=slug, persona=name, before=query.before)
    return await _runs(session, reader, wanted, query.limit)


async def _runs(
    session: Session, reader: Reader, wanted: calls.PersonaRunFilters, limit: int
) -> schemas.PersonaRunList:
    scope = reader.scope
    if reader.actor is None or scope is None:
        raise Forbidden(A_KEY_LISTS)
    found = await calls.runs_of_persona(session, scope, wanted, limit=limit)
    return schemas.PersonaRunList(runs=[_run_row(run) for run in found.runs], total=found.total, next=found.next)


def _run_row(run: calls.PersonaRun) -> schemas.PersonaRunRow:
    facts = calls.facts_of(run.facts)
    score = None
    if facts.judged is not None and facts.passed is not None:
        score = schemas.SessionScore(
            held=facts.held or 0, judged=facts.judged, passed=facts.passed, reason=facts.reason
        )
    return schemas.PersonaRunRow.model_validate(
        {
            "call": facts.call,
            "agent": run.agent,
            "persona": facts.persona,
            "started_at": run.started_at,
            "ended_at": facts.ended_at,
            "turns": len(facts.heard_at),
            "end_reason": facts.end_reason,
            "outcome": facts.outcome,
            "cost_usd": facts.cost_usd,
            "score": None if score is None else score.dump(),
            "played_by": _played_by(run),
            "caller_cost_usd": run.facts.caller_cost_usd,
        }
    )


def _played_by(run: calls.PersonaRun) -> dict[str, str | None] | None:
    facts = run.facts
    if facts.caller_llm is None:
        return None
    return {"llm": facts.caller_llm, "tts": facts.caller_tts, "voice": facts.caller_voice}


async def _brief_of(
    session: Session, serving: calls.Serving, actor: Actor, slug: str, body: judged.GeneratePersonas
) -> judging.Brief:
    scope: Scope = actor.scope
    registration = serving.registry.serving(scope, slug, None)
    declared = None if registration is None else registration.config
    newest = await calls.find_calls(session, scope, calls.ListFilters(agent=slug), limit=1)
    prompt = ""
    if newest.calls:
        prompt = await calls.prompt_of(session, scope.org, await serving.logs.store.whole(newest.calls[0]))
    call = ""
    if body.from_call is not None:
        entries, read_as = await readable(session, serving, actor, body.from_call)
        call = judging.conversation_of(judging.case_of(entries, read_as))
    template = None
    if body.template is not None:
        found = judging.library_personas().get(body.template)
        if found is None:
            raise NotFound(judging.NO_SUCH_PERSONA.format(name=body.template, agent=slug))
        template = found.persona
    tools: tuple[str, ...] = ()
    if declared is not None:
        tools = tuple(f"{tool.name}: {tool.description}" for tool in declared.tools)
    return judging.Brief(
        prompt=prompt,
        tools=tools,
        knowledge="" if declared is None or declared.knowledge is None else declared.knowledge,
        about=body.about,
        call=call,
        template=template,
    )
