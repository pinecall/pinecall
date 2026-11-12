"""The dataset endpoints: a call kept as a case or read as a golden, a case written by hand, listed, forgotten."""

from typing import Annotated

from fastapi import APIRouter, Path, Query

from runtime.calls import service as calls
from runtime.enums import CaseStatus
from runtime.judging import schemas
from runtime.judging.auth import EvalsKey, TheAllowedAgent, TheAllowedFilter, TheCase
from runtime.judging.service import cases
from runtime.postgres import Session
from runtime.wire.goldens import Golden

router = APIRouter()


# The case is the org's, played in the sandbox whichever env its call ran in; the key must be
# one that reads the call, as a replay's does. An expect left empty is the one the call's broken
# verdicts give.
@router.post("/v1/evals/cases", response_model_exclude_unset=True)
async def promote_case(body: schemas.PromoteCaseRequest, actor: EvalsKey, session: Session) -> schemas.CaseRow:
    """A finished call's caller lines kept as a case of the org's dataset."""
    finished = await calls.read_finished(session, actor, body.call)
    born = cases.Born(org=actor.org, env=finished.env, agent=finished.agent, version=finished.version)
    kept = await cases.promote_call(
        session, finished.entries, born, name=body.name, expect=body.expect, held_out=body.held_out, by=actor.asked_by
    )
    return schemas.CaseRow.of(kept)


# What `pinecall runs promote` writes to the agent's test/candidates: the same golden a case would hold,
# derived here once, kept nowhere.
@router.get("/v1/calls/{call}/golden", response_model_exclude_unset=True)
async def get_golden_of_call(
    call: str, actor: EvalsKey, session: Session, query: Annotated[schemas.GoldenQuery, Query()]
) -> Golden:
    """The golden a finished call makes from a seq on, its expect from its broken verdicts."""
    finished = await calls.read_finished(session, actor, call)
    return cases.golden_of_call(finished.entries, name=query.name, from_seq=query.from_seq)


# Written in the key's env, as a kept call is in its call's; played in the sandbox like every case.
@router.put("/v1/agents/{slug}/cases/{name}", response_model_exclude_unset=True)
async def write_case(
    slug: TheAllowedAgent,
    name: Annotated[str, Path(min_length=1)],
    body: schemas.WriteCaseRequest,
    actor: EvalsKey,
    session: Session,
) -> schemas.CaseRow:
    """Write a golden as a case of the agent, by hand; their own name again rewrites it."""
    writing = cases.Promoted(org=actor.org, env=actor.env, name=name, author=actor.asked_by, held_out=body.held_out)
    return schemas.CaseRow.of(await cases.write_case(session, body.golden, slug, writing))


@router.get("/v1/evals/cases", response_model_exclude_unset=True)
async def list_cases(
    actor: EvalsKey,
    session: Session,
    agent: TheAllowedFilter,
    status: Annotated[CaseStatus | None, Query()] = None,
) -> schemas.CaseList:
    """The org's cases, one agent's or every one, the pending first; how many wait, of how many."""
    found = await cases.list_cases(session, actor.org, agent, status)
    return schemas.CaseList(
        cases=[schemas.CaseRow.of(case) for case in found],
        pending=await cases.count_pending(session, actor.org, agent),
        pending_at_most=cases.PENDING_AT_MOST,
    )


@router.delete("/v1/evals/cases/{id}", status_code=204)
async def delete_case(case: TheCase, session: Session) -> None:
    """Forget one of the org's cases; another org's, or nobody's, is the same 404."""
    await cases.delete_case(session, case)
