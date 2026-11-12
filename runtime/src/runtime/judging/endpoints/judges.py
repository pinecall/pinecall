"""The judge endpoints: Pinecall's switched on or off, the org's own and an agent's."""

from collections.abc import Sequence
from dataclasses import asdict

from fastapi import APIRouter

from runtime.agents.auth import TheAgent
from runtime.judging import schemas
from runtime.judging.auth import EvalsKey
from runtime.judging.service import judges
from runtime.postgres import Session

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


def _read_body(body: schemas.JudgeRequest) -> judges.Wanted:
    return judges.Wanted(**body.model_dump(), named=frozenset(body.model_fields_set))


# A judge of the roster is its row by the same names: its question's fields beside whose it is.
def _list(roster: Sequence[judges.RosterJudge]) -> schemas.JudgeList:
    rows = [
        schemas.JudgeRow.model_validate({**asdict(judge), **asdict(judge.spec), "reads": judge.spec.list_reads()})
        for judge in roster
    ]
    return schemas.JudgeList(judges=rows)
