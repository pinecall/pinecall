"""The personas an agent is called by in its simulations."""

from collections.abc import Sequence
from typing import Any

from sqlalchemy import delete, func
from sqlalchemy.dialects.postgresql import insert as upsert

from runtime.judging.models import AgentPersona
from runtime.kit.repository import Repository


class PersonaRepository(Repository[AgentPersona]):
    """One row per org, agent and name."""

    model = AgentPersona

    async def list_of_agent(self, org: str, agent: str) -> Sequence[AgentPersona]:
        """The agent's callers, by name."""
        statement = (
            self.statement().where(AgentPersona.org == org, AgentPersona.agent == agent).order_by(AgentPersona.name)
        )
        return await self.all(statement)

    async def list_of_org(self, org: str) -> Sequence[AgentPersona]:
        """Every agent's callers, by agent and then by name."""
        return await self.all(
            self.statement().where(AgentPersona.org == org).order_by(AgentPersona.agent, AgentPersona.name)
        )

    async def find(self, org: str, agent: str, name: str) -> AgentPersona | None:
        """One of the agent's callers, by name, or None."""
        statement = self.statement().where(
            AgentPersona.org == org, AgentPersona.agent == agent, AgentPersona.name == name
        )
        return await self.one_or_none(statement)

    async def put(self, org: str, agent: str, *, name: str, author: str, **fields: Any) -> None:
        """Write one of the agent's callers whole; the same name again replaces it."""
        statement = upsert(AgentPersona).values(org=org, agent=agent, name=name, author=author, **fields)
        replaced = {key: statement.excluded[key] for key in (*fields, "author")}
        await self.session.execute(
            statement.on_conflict_do_update(
                index_elements=["org", "agent", "name"], set_={**replaced, "set_at": func.now()}
            )
        )

    async def delete_named(self, org: str, agent: str, name: str) -> bool:
        """Forget one of the agent's callers; whether it was there."""
        statement = delete(AgentPersona).where(
            AgentPersona.org == org, AgentPersona.agent == agent, AgentPersona.name == name
        )
        return await self.change(statement) > 0
