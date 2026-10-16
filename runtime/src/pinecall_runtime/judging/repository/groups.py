"""Cases grouped by what broke them: one open group per agent and judge, its cause, its proposal."""

from dataclasses import dataclass
from typing import Any

from sqlalchemy import func, select, text, update
from sqlalchemy.dialects.postgresql import insert as upsert

from pinecall_runtime.enums import CaseSource, CaseStatus
from pinecall_runtime.judging.models import OPEN_GROUP, CaseGroup, EvalCase
from pinecall_runtime.kit.repository import Repository


@dataclass(frozen=True, slots=True)
class GroupCounted:
    """A group with its cases counted, as a list shows it."""

    group: CaseGroup
    cases: int
    simulations: int


class GroupRepository(Repository[CaseGroup]):
    """One open group per org, agent and judge (case_groups_one_open); decided ones stay."""

    model = CaseGroup

    # Racing seals: the second insert finds the open group the first made and adds nothing.
    async def open(self, *, id: str, org: str, agent: str, judge: str, cause: str) -> None:
        """Open the agent's group for the judge, unless one is open already."""
        statement = upsert(CaseGroup).values(id=id, org=org, agent=agent, judge=judge, cause=cause)
        await self.session.execute(
            statement.on_conflict_do_nothing(index_elements=["org", "agent", "judge"], index_where=text(OPEN_GROUP))
        )

    async def join(self, org: str, agent: str, judge: str, case: str) -> str | None:
        """Put the case in the agent's open group for the judge; the group's id, or None."""
        open_group = (
            select(CaseGroup.id)
            .where(
                CaseGroup.org == org,
                CaseGroup.agent == agent,
                CaseGroup.judge == judge,
                CaseGroup.status == CaseStatus.pending,
            )
            .scalar_subquery()
        )
        statement = (
            update(EvalCase)
            .where(EvalCase.id == case, EvalCase.org == org)
            .values(group_id=open_group)
            .returning(EvalCase.group_id)
        )
        return (await self.session.execute(statement)).scalar_one_or_none()

    async def listed(self, org: str, agent: str | None = None, group: str | None = None) -> list[GroupCounted]:
        """The org's groups with their counts, one agent's or every one, the pending first and newest first."""
        simulated = func.count(EvalCase.id).filter(EvalCase.source == CaseSource.simulation)
        statement = (
            select(CaseGroup, func.count(EvalCase.id), simulated)
            .outerjoin(EvalCase, EvalCase.group_id == CaseGroup.id)
            .where(CaseGroup.org == org)
            .group_by(CaseGroup.id)
            .order_by((CaseGroup.status == CaseStatus.pending).desc(), CaseGroup.since.desc())
        )
        if agent is not None:
            statement = statement.where(CaseGroup.agent == agent)
        if group is not None:
            statement = statement.where(CaseGroup.id == group)
        rows = (await self.session.execute(statement)).all()
        return [GroupCounted(found, int(cases), int(simulations)) for found, cases, simulations in rows]

    async def propose(self, org: str, group: str, *, cause: str, proposal: dict[str, Any]) -> bool:
        """Keep a diagnosis on its group: its cause line, and the proposal whole; whether found."""
        statement = (
            update(CaseGroup)
            .where(CaseGroup.id == group, CaseGroup.org == org)
            .values(cause=cause, proposal=proposal, proposed_at=func.now())
        )
        return await self.changed(statement) > 0

    async def decide(self, org: str, group: str, *, status: CaseStatus, by: str) -> bool:
        """Approve or dismiss a group and every case in it still waiting; whether found."""
        decided = update(CaseGroup).where(CaseGroup.id == group, CaseGroup.org == org).values(status=status)
        if await self.changed(decided) == 0:
            return False
        cases = (
            update(EvalCase)
            .where(EvalCase.group_id == group, EvalCase.org == org, EvalCase.status == CaseStatus.pending)
            .values(status=status, decided_by=by, decided_at=func.now())
        )
        await self.changed(cases)
        return True
