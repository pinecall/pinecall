"""The org's dataset: cases born at hang-up or kept by hand, listed, picked for a run, grouped, decided."""

from collections.abc import Sequence

from sqlalchemy import ColumnElement, exists, func, literal, select, update
from sqlalchemy.dialects.postgresql import insert as upsert

from runtime.enums import CaseStatus
from runtime.judging.models import CaseGroup, EvalCase
from runtime.kit.repository import Repository

# What a case born at hang-up is written with; every other column takes its default.
BORN_WITH = (
    "id",
    "org",
    "agent",
    "name",
    "golden",
    "source_call",
    "source_env",
    "held_out",
    "author",
    "status",
    "broke",
    "source_version",
    "source",
    "persona",
)


class CaseRepository(Repository[EvalCase]):
    """One row per case; a name is one case per agent."""

    model = EvalCase

    # One statement, so two seals at once never both pass the count: the second finds the first.
    async def create_pending(self, case: EvalCase, *, at_most: int) -> str | None:
        """Keep a call that broke as a pending case, unless the agent's inbox is full or holds the call; its id."""
        pending = (
            select(func.count())
            .where(EvalCase.org == case.org, EvalCase.agent == case.agent, EvalCase.status == CaseStatus.pending)
            .scalar_subquery()
        )
        already = exists(select(EvalCase.id).where(EvalCase.org == case.org, EvalCase.source_call == case.source_call))
        columns = EvalCase.__table__.columns
        row = select(*(literal(getattr(case, name), type_=columns[name].type) for name in BORN_WITH)).where(
            pending < at_most, ~already
        )
        statement = upsert(EvalCase).from_select(list(BORN_WITH), row).on_conflict_do_nothing().returning(EvalCase.id)
        return (await self.session.execute(statement)).scalar_one_or_none()

    async def list_of_org(
        self, org: str, agent: str | None, status: CaseStatus | None = None, group: str | None = None
    ) -> Sequence[EvalCase]:
        """The org's cases, one agent's or every one, one status or group or all, pending first."""
        statement = self.statement().where(EvalCase.org == org)
        if agent is not None:
            statement = statement.where(EvalCase.agent == agent)
        if status is not None:
            statement = statement.where(EvalCase.status == status)
        if group is not None:
            statement = statement.where(EvalCase.group_id == group)
        ordered = statement.order_by(
            EvalCase.agent, (EvalCase.status == CaseStatus.pending).desc(), EvalCase.created_at.desc(), EvalCase.name
        )
        return await self.all(ordered)

    async def count_pending(self, org: str, agent: str | None) -> int:
        """How many cases wait for a person, one agent's or the org's."""
        statement = self.statement().where(EvalCase.org == org, EvalCase.status == CaseStatus.pending)
        if agent is not None:
            statement = statement.where(EvalCase.agent == agent)
        return await self.count(statement)

    # A nightly run reads what a person approved and the repository does not hold; a case named is
    # read whatever its status, so a pending one can be reproduced before it is decided.
    async def list_for_run(self, org: str, agent: str, names: Sequence[str], *, every: bool) -> Sequence[EvalCase]:
        """The cases named, and with `every`, the approved ones not held out nor kept in the repo."""
        chosen: ColumnElement[bool] = EvalCase.name.in_(list(names))
        if every:
            approved = (EvalCase.status == CaseStatus.approved) & ~EvalCase.held_out & ~EvalCase.kept_in_repo
            chosen = chosen | approved
        statement = self.statement().where(EvalCase.org == org, EvalCase.agent == agent, chosen).order_by(EvalCase.name)
        return await self.all(statement)

    async def find_named(self, org: str, agent: str, name: str) -> EvalCase | None:
        """The agent's case of that name, or None."""
        statement = self.statement().where(EvalCase.org == org, EvalCase.agent == agent, EvalCase.name == name)
        return await self.one_or_none(statement)

    async def find(self, org: str, case: str) -> EvalCase | None:
        """One of the org's cases, or None for another org's or nobody's."""
        return await self.one_or_none(self.statement().where(EvalCase.id == case, EvalCase.org == org))

    async def set_group(self, org: str, agent: str, judge: str, case: str) -> str | None:
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

    async def decide_pending_in(self, org: str, group: str, *, status: CaseStatus, by: str) -> int:
        """Decide every case of the group still waiting, as its group was; how many."""
        statement = (
            update(EvalCase)
            .where(EvalCase.group_id == group, EvalCase.org == org, EvalCase.status == CaseStatus.pending)
            .values(status=status, decided_by=by, decided_at=func.now())
        )
        return await self.change(statement)

    async def list_statuses_in(self, org: str, group: str) -> set[CaseStatus]:
        """The statuses the group's cases are in."""
        statement = select(EvalCase.status).where(EvalCase.group_id == group, EvalCase.org == org)
        return set((await self.session.execute(statement)).scalars())
