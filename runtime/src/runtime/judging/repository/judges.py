"""The judges an org writes, the org's (agent '') and one agent's own, and a name a class already holds."""

from collections.abc import Sequence
from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert as upsert

from runtime.actor import THE_ORGS_OWN
from runtime.agents.models import AgentDeclaration
from runtime.judging.models import AgentJudge
from runtime.kit.repository import Repository


class JudgeRepository(Repository[AgentJudge]):
    """One row per org, level (the org's is agent '') and name."""

    model = AgentJudge

    # The org's rows first: their agent is '', which sorts before any slug.
    async def list_for_call(self, org: str, agent: str) -> Sequence[AgentJudge]:
        """Every judge a call of the agent is held to: the org's, then its own; for agent '', the org's alone."""
        statement = (
            self.statement()
            .where(AgentJudge.org == org, AgentJudge.agent.in_([THE_ORGS_OWN, agent]))
            .order_by(AgentJudge.agent, AgentJudge.name)
        )
        return await self.all(statement)

    # A name is one question per call: the org's and an agent's may not share it, since a call of
    # that agent would carry two verdicts under one name. Two agents may.
    async def find_clash(self, org: str, agent: str, name: str) -> str | None:
        """The other level that holds the name already, or None."""
        statement = (
            select(AgentJudge.agent)
            .where(
                AgentJudge.org == org,
                AgentJudge.name == name,
                AgentJudge.agent != agent,
                AgentJudge.agent.in_([THE_ORGS_OWN, agent]) | (agent == THE_ORGS_OWN),
            )
            .limit(1)
        )
        found = (await self.session.execute(statement)).scalar_one_or_none()
        return None if found is None else str(found)

    # Read off what each agent's app last declared, as the wire carried it: `judges.own[].name`. A
    # class is refused the org's name where it declares itself; this is the same rule the other way.
    async def find_class_holding(self, org: str, name: str) -> str | None:
        """An agent of the org whose class declares a judge of its own under the name, or None."""
        own = AgentDeclaration.declaration["judges"]["own"]
        statement = (
            select(AgentDeclaration.agent)
            .where(AgentDeclaration.org == org, own.contains([{"name": name}]))
            .order_by(AgentDeclaration.agent)
            .limit(1)
        )
        found = (await self.session.execute(statement)).scalar_one_or_none()
        return None if found is None else str(found)

    async def put(self, org: str, agent: str, *, name: str, author: str, **fields: Any) -> None:
        """Write a judge whole; the same name again replaces it."""
        statement = upsert(AgentJudge).values(org=org, agent=agent, name=name, author=author, **fields)
        replaced = {key: statement.excluded[key] for key in (*fields, "author")}
        await self.session.execute(
            statement.on_conflict_do_update(
                index_elements=["org", "agent", "name"], set_={**replaced, "set_at": func.now()}
            )
        )

    async def delete_named(self, org: str, agent: str, name: str) -> bool:
        """Forget a judge at one level; whether it was there."""
        statement = delete(AgentJudge).where(AgentJudge.org == org, AgentJudge.agent == agent, AgentJudge.name == name)
        return await self.change(statement) > 0
