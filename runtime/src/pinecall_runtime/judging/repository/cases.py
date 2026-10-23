"""The org's dataset: cases born at hang-up or kept by hand, listed, picked for a run, decided."""

from collections.abc import Sequence
from typing import Any

from sqlalchemy import ColumnElement, exists, func, literal, select
from sqlalchemy.dialects.postgresql import insert as upsert

from pinecall_runtime.enums import CaseSource, CaseStatus, Env
from pinecall_runtime.judging.models import EvalCase
from pinecall_runtime.kit.repository import Repository


class CaseRepository(Repository[EvalCase]):
    """One row per case; a name is one case per agent."""

    model = EvalCase

    # One statement, so two seals at once never both pass the count: the second finds the first.
    async def born(
        self,
        *,
        id: str,
        org: str,
        agent: str,
        name: str,
        golden: dict[str, Any],
        source_call: str,
        source_env: Env,
        author: str,
        broke: list[dict[str, Any]],
        source_version: int | None,
        source: CaseSource,
        persona: str | None,
        at_most: int,
    ) -> str | None:
        """Keep a call that broke as a pending case, unless the agent's inbox is full; its id."""
        pending = (
            select(func.count())
            .where(EvalCase.org == org, EvalCase.agent == agent, EvalCase.status == CaseStatus.pending)
            .scalar_subquery()
        )
        already = exists(select(EvalCase.id).where(EvalCase.org == org, EvalCase.source_call == source_call))
        columns = [
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
        ]
        row = select(
            literal(id),
            literal(org),
            literal(agent),
            literal(name),
            literal(golden, type_=EvalCase.golden.type),
            literal(source_call),
            literal(source_env, type_=EvalCase.source_env.type),
            literal(False),
            literal(author),
            literal(CaseStatus.pending, type_=EvalCase.status.type),
            literal(broke, type_=EvalCase.broke.type),
            literal(source_version),
            literal(source, type_=EvalCase.source.type),
            literal(persona),
        ).where(pending < at_most, ~already)
        statement = upsert(EvalCase).from_select(columns, row).on_conflict_do_nothing().returning(EvalCase.id)
        return (await self.session.execute(statement)).scalar_one_or_none()

    async def listed(
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

    async def waiting(self, org: str, agent: str | None) -> int:
        """How many cases wait for a person, one agent's or the org's."""
        statement = self.statement().where(EvalCase.org == org, EvalCase.status == CaseStatus.pending)
        if agent is not None:
            statement = statement.where(EvalCase.agent == agent)
        return await self.count(statement)

    # A nightly run reads what a person approved and the repository does not hold; a case named is
    # read whatever its status, so a pending one can be reproduced before it is decided.
    async def picked(self, org: str, agent: str, names: Sequence[str], *, every: bool) -> Sequence[EvalCase]:
        """The cases named, and with `every`, the approved ones not held out nor kept in the repo."""
        chosen: ColumnElement[bool] = EvalCase.name.in_(list(names))
        if every:
            approved = (EvalCase.status == CaseStatus.approved) & ~EvalCase.held_out & ~EvalCase.kept_in_repo
            chosen = chosen | approved
        statement = self.statement().where(EvalCase.org == org, EvalCase.agent == agent, chosen).order_by(EvalCase.name)
        return await self.all(statement)

    async def named(self, org: str, agent: str, name: str) -> EvalCase | None:
        """The agent's case of that name, or None."""
        statement = self.statement().where(EvalCase.org == org, EvalCase.agent == agent, EvalCase.name == name)
        return await self.one_or_none(statement)

    async def get(self, org: str, case: str) -> EvalCase | None:
        """One of the org's cases, or None for another org's or nobody's."""
        return await self.one_or_none(self.statement().where(EvalCase.id == case, EvalCase.org == org))
