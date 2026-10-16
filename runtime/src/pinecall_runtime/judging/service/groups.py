"""Cases grouped by what broke them: one open group per agent and judge, its cause, its proposal."""

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from pinecall_runtime.enums import CaseStatus
from pinecall_runtime.exceptions import NotFound
from pinecall_runtime.judging.repository import GroupCounted, GroupRepository
from pinecall_runtime.judging.schemas import GroupRow, ProposalRow
from pinecall_runtime.kit.crypto import random_id

A_GROUP = "grp_"
NO_SUCH_GROUP = "no case group {id} in this key's org"


async def join_group(session: AsyncSession, org: str, agent: str, judge: str, case: str, *, cause: str) -> str | None:
    """Put a case kept at hang-up in its agent's open group for the judge, opened if need be."""
    repository = GroupRepository(session)
    await repository.open(id=random_id(A_GROUP, 6), org=org, agent=agent, judge=judge, cause=cause)
    return await repository.join(org, agent, judge, case)


async def list_groups(session: AsyncSession, org: str, agent: str | None) -> list[GroupRow]:
    """The org's groups, one agent's or every one, the pending ones first and newest first."""
    return [group_row(found) for found in await GroupRepository(session).listed(org, agent)]


async def get_group(session: AsyncSession, org: str, group: str) -> GroupRow:
    """One of the org's groups; another org's, or nobody's, is a 404."""
    found = await GroupRepository(session).listed(org, group=group)
    if not found:
        raise NotFound(NO_SUCH_GROUP.format(id=group))
    return group_row(found[0])


async def propose_for_group(session: AsyncSession, org: str, group: str, proposal: dict[str, Any]) -> None:
    """Keep a diagnosis on its group: its cause line, and the proposal whole."""
    cause = str(proposal.get("cause") or "")
    if not await GroupRepository(session).propose(org, group, cause=cause, proposal=proposal):
        raise NotFound(NO_SUCH_GROUP.format(id=group))


async def decide_group(session: AsyncSession, org: str, group: str, *, status: CaseStatus, by: str) -> None:
    """Approve or dismiss a group and every case in it still waiting."""
    if not await GroupRepository(session).decide(org, group, status=status, by=by):
        raise NotFound(NO_SUCH_GROUP.format(id=group))


def group_row(found: GroupCounted) -> GroupRow:
    """A group as the endpoints send it."""
    group = found.group
    return GroupRow(
        id=group.id,
        agent=group.agent,
        judge=group.judge,
        cause=group.cause,
        status=group.status,
        since=group.since,
        cases=found.cases,
        simulations=found.simulations,
        proposal=None if group.proposal is None else ProposalRow.model_validate(group.proposal),
        proposed_at=group.proposed_at,
    )
