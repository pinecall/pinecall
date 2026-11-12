"""Cases grouped by what broke them: one open group per agent and judge, its cause, its proposal, its decision."""

from collections.abc import Sequence
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from runtime.enums import CaseStatus
from runtime.exceptions import NotFound, ValidationError
from runtime.judging.repository.cases import CaseRepository
from runtime.judging.repository.groups import GroupCounted, GroupRepository
from runtime.kit.crypto import random_id

A_GROUP = "grp_"
NO_SUCH_GROUP = "no case group {id} in this key's org"
WRONG_ONLY_WHEN_DISMISSED = (
    "judge_was_wrong says the group's judge broke where it should have held, so it dismisses the "
    "group: send it with status dismissed"
)


async def join_group(session: AsyncSession, org: str, agent: str, judge: str, case: str, *, cause: str) -> str | None:
    """Put a case kept at hang-up in its agent's open group for the judge, opened if need be."""
    await GroupRepository(session).open(id=random_id(A_GROUP, 6), org=org, agent=agent, judge=judge, cause=cause)
    return await CaseRepository(session).set_group(org, agent, judge, case)


async def list_groups(session: AsyncSession, org: str, agent: str | None) -> Sequence[GroupCounted]:
    """The org's groups, one agent's or every one, the pending ones first and newest first."""
    return await GroupRepository(session).list_counted(org, agent)


async def get_group(session: AsyncSession, org: str, group: str) -> GroupCounted:
    """One of the org's groups; another org's, or nobody's, is a 404."""
    found = await GroupRepository(session).list_counted(org, group=group)
    if not found:
        raise NotFound(NO_SUCH_GROUP.format(id=group))
    return found[0]


async def propose_for_group(session: AsyncSession, org: str, group: str, proposal: dict[str, Any]) -> GroupCounted:
    """Keep a diagnosis on its group: its cause line, and the proposal whole; the group after."""
    cause = str(proposal.get("cause") or "")
    if not await GroupRepository(session).propose(org, group, cause=cause, proposal=proposal):
        raise NotFound(NO_SUCH_GROUP.format(id=group))
    return await get_group(session, org, group)


# Until 2026-11 the endpoint knew the rule and the repository wrote both tables. The judge called
# wrong is a calibration label of each call of the group, which is whoever calibrates' to write.
async def decide_group(
    session: AsyncSession, org: str, group: str, *, status: CaseStatus, judge_was_wrong: bool = False, by: str
) -> GroupCounted:
    """Approve or dismiss a group and every case in it still waiting; the group after."""
    if judge_was_wrong and status is not CaseStatus.dismissed:
        raise ValidationError(WRONG_ONLY_WHEN_DISMISSED)
    if not await GroupRepository(session).set_status(org, group, status):
        raise NotFound(NO_SUCH_GROUP.format(id=group))
    await CaseRepository(session).decide_pending_in(org, group, status=status, by=by)
    return await get_group(session, org, group)


# Decided case by case, a group is decided once nothing in it waits: approved when a person approved
# any case of it, else dismissed. Left pending, it was the first of `cases groups` for ever. The
# group's row is taken first: of two requests deciding its last two cases at once, each saw the
# other's case still waiting and neither settled it (until 2026-11); now the second waits for the
# first's commit and reads what it wrote.
async def settle_group(session: AsyncSession, org: str, group: str) -> None:
    """Decide a group a person decided case by case, once none of its cases waits."""
    repository = GroupRepository(session)
    locked = await repository.lock(org, group)
    if locked is None or locked.status is not CaseStatus.pending:
        return
    found = await CaseRepository(session).list_statuses_in(org, group)
    if not found or CaseStatus.pending in found:
        return
    decided = CaseStatus.approved if CaseStatus.approved in found else CaseStatus.dismissed
    await repository.set_status(org, group, decided)
