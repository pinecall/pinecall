"""Cases grouped by what broke them: one open group per agent and judge, its cause, its proposal."""

from dataclasses import dataclass
from typing import Any

from sqlalchemy import func, select, text, update
from sqlalchemy.dialects.postgresql import insert as upsert

from runtime.enums import CaseSource, CaseStatus
from runtime.judging.models import OPEN_GROUP, CaseGroup, EvalCase
from runtime.kit.repository import Repository


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

    async def list_counted(self, org: str, agent: str | None = None, group: str | None = None) -> list[GroupCounted]:
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
        return await self.change(statement) > 0

    async def set_status(self, org: str, group: str, status: CaseStatus) -> bool:
        """Approve or dismiss a group; whether found."""
        decided = update(CaseGroup).where(CaseGroup.id == group, CaseGroup.org == org).values(status=status)
        return await self.change(decided) > 0

    # Held to the end of the transaction: whoever settles a group reads its cases with the row taken,
    # so of two requests deciding its last two cases at once the second waits and sees the first's.
    async def lock(self, org: str, group: str) -> CaseGroup | None:
        """The group with its row locked for this transaction, or None for another org's or nobody's."""
        statement = self.statement().where(CaseGroup.id == group, CaseGroup.org == org).with_for_update()
        return await self.one_or_none(statement.execution_options(populate_existing=True))
