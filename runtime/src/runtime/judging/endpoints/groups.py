"""The case group endpoints: what broke an agent, and every case of one group."""

from fastapi import APIRouter

from runtime.agents.auth import KnownFilter
from runtime.judging import schemas
from runtime.judging.auth import EvalsKey, TheGroup
from runtime.judging.service import cases, groups
from runtime.postgres import Session

router = APIRouter()


@router.get("/v1/evals/groups")
async def list_groups(actor: EvalsKey, session: Session, agent: KnownFilter) -> schemas.GroupList:
    """The org's case groups, one agent's or every one, the pending first and newest first."""
    found = await groups.list_groups(session, actor.org, agent)
    rows = [schemas.GroupRow.of_counted(one.group, cases=one.cases, simulations=one.simulations) for one in found]
    return schemas.GroupList(groups=rows)


@router.get("/v1/evals/groups/{id}")
async def get_group(found: TheGroup, actor: EvalsKey, session: Session) -> schemas.GroupWhole:
    """One group and every case in it."""
    group = schemas.GroupRow.of_counted(found.group, cases=found.cases, simulations=found.simulations)
    kept = await cases.list_cases(session, actor.org, group.agent, group=group.id)
    return schemas.GroupWhole(group=group, cases=[schemas.CaseRow.of(case) for case in kept])
