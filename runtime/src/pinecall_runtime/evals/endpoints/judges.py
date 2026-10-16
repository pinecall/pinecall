"""The judge endpoints: Pinecall's switched on or off, the org's own and an agent's, and a try."""

from fastapi import APIRouter

from pinecall_runtime.calls import service as calls
from pinecall_runtime.calls.auth import TheServing
from pinecall_runtime.evals.auth import EvalsKey
from pinecall_runtime.evals.endpoints.reading import asked_by, is_over, readable
from pinecall_runtime.exceptions import ValidationError
from pinecall_runtime.judging import schemas
from pinecall_runtime.judging import service as judging
from pinecall_runtime.kit.auth import THE_ORGS_OWN, Actor, Scope
from pinecall_runtime.postgres import Session
from pinecall_runtime.wire.scores import CallScore, EvalsSpent

router = APIRouter()

ONE_OR_THE_OTHER = "a try names the agent's last calls or the calls themselves, never both"
NOTHING_TO_TRY = "a try names the agent's last calls (last) or the calls themselves (calls)"
NOT_FINISHED = "the call has not finished"
ON_SIMULATIONS = "{name} runs on calls a simulated caller played, and a person made this one"


# One list for both envs, as the agent's personas are.
@router.get("/v1/org/judges")
async def list_org_judges(actor: EvalsKey, session: Session) -> schemas.JudgeList:
    """Pinecall's judges as the org switched them, then the org's own, asked of every agent."""
    return schemas.JudgeList(judges=await judging.list_judges(session, actor.org, THE_ORGS_OWN))


@router.put("/v1/org/judges/{name}")
async def put_org_judge(name: str, body: schemas.JudgeRequest, actor: EvalsKey, session: Session) -> schemas.JudgeList:
    """One of Pinecall's switched for every agent, or one of the org's own written whole."""
    await judging.write_judge(session, actor.org, THE_ORGS_OWN, name, body, by=asked_by(actor))
    return schemas.JudgeList(judges=await judging.list_judges(session, actor.org, THE_ORGS_OWN))


@router.delete("/v1/org/judges/{name}")
async def delete_org_judge(name: str, actor: EvalsKey, session: Session) -> schemas.JudgeList:
    """Forget one of the org's own judges; 404 for a name nobody wrote, 409 for Pinecall's."""
    await judging.delete_judge(session, actor.org, THE_ORGS_OWN, name)
    return schemas.JudgeList(judges=await judging.list_judges(session, actor.org, THE_ORGS_OWN))


@router.get("/v1/agents/{slug}/judges")
async def list_judges(slug: str, actor: EvalsKey, session: Session) -> schemas.JudgeList:
    """Every judge the agent's calls may meet: Pinecall's, the org's own, the agent's own."""
    return schemas.JudgeList(judges=await judging.list_judges(session, actor.org, slug))


@router.put("/v1/agents/{slug}/judges/{name}")
async def put_judge(
    slug: str, name: str, body: schemas.JudgeRequest, actor: EvalsKey, session: Session
) -> schemas.JudgeList:
    """One of Pinecall's switched for this agent, or one of its own written whole."""
    await judging.write_judge(session, actor.org, slug, name, body, by=asked_by(actor))
    return schemas.JudgeList(judges=await judging.list_judges(session, actor.org, slug))


@router.delete("/v1/agents/{slug}/judges/{name}")
async def delete_judge(slug: str, name: str, actor: EvalsKey, session: Session) -> schemas.JudgeList:
    """Forget one of the agent's own judges; 404 for a name nobody wrote, 409 for Pinecall's."""
    await judging.delete_judge(session, actor.org, slug, name)
    return schemas.JudgeList(judges=await judging.list_judges(session, actor.org, slug))


# Asked as the seal asks it, on the model the seal would judge the call on, and written on no log.
@router.post("/v1/agents/{slug}/judges/try")
async def try_judge(
    slug: str, body: schemas.JudgeTry, actor: EvalsKey, serving: TheServing, session: Session
) -> schemas.JudgeTried:
    """Ask one judge, written or only in the body, of finished calls of the agent."""
    if body.last is not None and body.calls:
        raise ValidationError(ONE_OR_THE_OTHER)
    spec = (
        judging.spec_of(body.name, body)
        if body.question.strip()
        else await judging.judge_named(session, actor.org, slug, body.name)
    )
    named = body.calls or await _newest(session, actor.scope, slug, body.last)
    tried = [await _tried(session, serving, actor, call, spec) for call in named]
    scores = [score for _, score in tried]
    trial = EvalsSpent(
        kind="try",
        name=spec.name,
        env=actor.env,
        calls=named,
        evals=sum(score.evals for score in scores),
        judge_calls=sum(score.judge_calls for score in scores),
        judge_cost_usd=sum(score.judge_cost_usd or 0.0 for score in scores) or None,
        own_key=any(score.own_key for score in scores),
    )
    if trial.judge_calls:
        await serving.logs.agent(slug).append("evals.spent", trial.dump())
    return schemas.JudgeTried(rows=[row for row, _ in tried], evals=trial.evals, cost_usd=trial.judge_cost_usd or 0.0)


# The newest finished calls: a page of the list at a time, the calls still going left out.
async def _newest(session: Session, scope: Scope, agent: str, last: int | None) -> list[str]:
    if last is None:
        raise ValidationError(NOTHING_TO_TRY)
    finished: list[str] = []
    before: str | None = None
    while len(finished) < last:
        found = await calls.find_calls(session, scope, calls.ListFilters(agent=agent, before=before), limit=last)
        sealed = await calls.sealed_among(session, found.calls)
        finished += [call for call in found.calls if call in sealed]
        if found.next is None:
            break
        before = found.next
    return finished[:last]


async def _tried(
    session: Session, serving: calls.Serving, actor: Actor, call: str, spec: judging.JudgeSpec
) -> tuple[schemas.JudgeTriedRow, CallScore]:
    entries, declared = await readable(session, serving, actor, call)
    if not is_over(entries):
        return _not_judged(call, NOT_FINISHED)
    if spec.on is judging.JudgeRunsWhen.simulations and not judging.case_of(entries, declared).simulated:
        return _not_judged(call, ON_SIMULATIONS.format(name=spec.name))
    panel = judging.alone(spec, await calls.panel_for(session, actor.org, entries, declared))
    score = await calls.judge_call(session, serving, entries, declared, panel, actor.scope)
    judgment = next(iter(score.judges), None)
    return schemas.JudgeTriedRow(call=call, judgment=judgment, not_judged=score.not_judged), score


def _not_judged(call: str, why: str) -> tuple[schemas.JudgeTriedRow, CallScore]:
    unjudged = CallScore(judges=[], judge_calls=0, not_judged=why)
    return schemas.JudgeTriedRow(call=call, judgment=None, not_judged=why), unjudged
