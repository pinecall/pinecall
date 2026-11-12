"""The judge endpoints: Pinecall's switched on or off, the org's own and an agent's."""

from collections.abc import Sequence
from dataclasses import asdict
from typing import Annotated

from fastapi import APIRouter, Query

from runtime.agents.auth import KnownAgent, TheAgent
from runtime.evals.auth import TheHarness
from runtime.evals.service import trials
from runtime.judging import schemas
from runtime.judging.auth import EvalsKey
from runtime.judging.service import judges
from runtime.postgres import Session
from runtime.wire.scores import CallScore

router = APIRouter()


# One list for both envs, as the agent's personas are.
@router.get("/v1/org/judges")
async def list_org_judges(actor: EvalsKey, session: Session) -> schemas.JudgeList:
    """Pinecall's judges as the org switched them, then the org's own, asked of every agent."""
    return _list(await judges.list_judges(session, actor.org, None))


@router.put("/v1/org/judges/{name}")
async def put_org_judge(name: str, body: schemas.JudgeRequest, actor: EvalsKey, session: Session) -> schemas.JudgeList:
    """One of Pinecall's switched for every agent, or one of the org's own written whole."""
    return _list(await judges.write_judge(session, actor.org, None, name, _read_body(body), by=actor.asked_by))


@router.delete("/v1/org/judges/{name}")
async def delete_org_judge(name: str, actor: EvalsKey, session: Session) -> schemas.JudgeList:
    """Forget one of the org's own judges; 404 for a name nobody wrote, 409 for Pinecall's."""
    return _list(await judges.delete_judge(session, actor.org, None, name))


# An agent whose class declares its judges lists the class's, each `fixed` (`owner: "class"` for its own),
# and writes none of them here: a PUT or a DELETE is 409 naming the class.
@router.get("/v1/agents/{slug}/judges")
async def list_judges(agent: TheAgent, actor: EvalsKey, session: Session) -> schemas.JudgeList:
    """Every judge the agent's calls may meet: Pinecall's, the org's own, the agent's own or its class's."""
    return _list(await judges.list_judges(session, actor.org, agent))


@router.put("/v1/agents/{slug}/judges/{name}")
async def put_judge(
    agent: TheAgent, name: str, body: schemas.JudgeRequest, actor: EvalsKey, session: Session
) -> schemas.JudgeList:
    """One of Pinecall's switched for this agent, or one of its own written whole; 409 while its class declares them."""
    return _list(await judges.write_judge(session, actor.org, agent, name, _read_body(body), by=actor.asked_by))


@router.delete("/v1/agents/{slug}/judges/{name}")
async def delete_judge(agent: TheAgent, name: str, actor: EvalsKey, session: Session) -> schemas.JudgeList:
    """Forget one of the agent's own judges; 404 for a name nobody wrote, 409 for Pinecall's or the class's."""
    return _list(await judges.delete_judge(session, actor.org, agent, name))


# Asked as the seal asks it, on the model the seal would judge the call on, and written on no log. The
# use case is evals': it reads finished calls, which stand above this domain.
@router.post("/v1/agents/{slug}/judges/try")
async def try_judge(slug: KnownAgent, body: schemas.JudgeTry, actor: EvalsKey, parts: TheHarness) -> schemas.JudgeTried:
    """Ask one judge, written or only in the body, of finished calls of the agent."""
    written = _read_body(body) if body.question.strip() else None
    trial = await trials.try_judge(parts, actor, slug, body.name, written, last=body.last, named=body.calls)
    return schemas.JudgeTried.of(trial)


# Hang-up judging run later: the org judged nothing then, the judge failed, or a judge again.
@router.post("/v1/evals/judge/{call}", response_model_exclude_unset=True)
async def judge_call(
    call: str, actor: EvalsKey, parts: TheHarness, query: Annotated[schemas.JudgeQuery, Query()]
) -> CallScore:
    """Judge a finished call, write the verdict on its log, and answer it."""
    return await trials.judge_again(parts, actor, call, again=query.again)


def _read_body(body: schemas.JudgeRequest) -> judges.Wanted:
    said = body.model_dump(include=set(schemas.JudgeRequest.model_fields))
    return judges.Wanted(**said, named=frozenset(body.model_fields_set))


# A judge of the roster is its row by the same names: its question's fields beside whose it is.
def _list(roster: Sequence[judges.RosterJudge]) -> schemas.JudgeList:
    rows = [
        schemas.JudgeRow.model_validate({**asdict(judge), **asdict(judge.spec), "reads": judge.spec.list_reads()})
        for judge in roster
    ]
    return schemas.JudgeList(judges=rows)
