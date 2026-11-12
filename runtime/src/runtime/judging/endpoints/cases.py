"""The dataset endpoints: a case written by hand, the inbox, a case forgotten."""

from typing import Annotated

from fastapi import APIRouter, Path, Query

from runtime.enums import CaseStatus
from runtime.judging import schemas
from runtime.judging.auth import EvalsKey, TheAllowedAgent, TheAllowedFilter, TheCase
from runtime.judging.service import cases
from runtime.postgres import Session

router = APIRouter()


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
