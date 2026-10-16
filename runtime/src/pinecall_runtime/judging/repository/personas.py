"""The personas an agent is called by in its simulations, and which of the library's it plays."""

from collections.abc import Sequence
from typing import Any

from sqlalchemy import delete, func
from sqlalchemy.dialects.postgresql import insert as upsert

from pinecall_runtime.judging.models import AgentPersona, PersonaSwitch
from pinecall_runtime.kit.auth import THE_ORGS_OWN
from pinecall_runtime.kit.repository import Repository


class PersonaRepository(Repository[AgentPersona]):
    """One row per org, agent and name."""

    model = AgentPersona

    async def of_agent(self, org: str, agent: str) -> Sequence[AgentPersona]:
        """The agent's callers, by name."""
        statement = (
            self.statement().where(AgentPersona.org == org, AgentPersona.agent == agent).order_by(AgentPersona.name)
        )
        return await self.all(statement)

    async def of_org(self, org: str) -> Sequence[AgentPersona]:
        """Every agent's callers, by agent and then by name."""
        return await self.all(
            self.statement().where(AgentPersona.org == org).order_by(AgentPersona.agent, AgentPersona.name)
        )

    async def get(self, org: str, agent: str, name: str) -> AgentPersona | None:
        """One of the agent's callers, by name."""
        statement = self.statement().where(
            AgentPersona.org == org, AgentPersona.agent == agent, AgentPersona.name == name
        )
        return await self.one_or_none(statement)

    async def put(self, org: str, agent: str, *, name: str, author: str, **fields: Any) -> None:
        """Write one of the agent's callers whole; the same name again replaces it."""
        values = {"org": org, "agent": agent, "name": name, "author": author, **fields}
        statement = upsert(AgentPersona).values(**values)
        replaced = {key: statement.excluded[key] for key in (*fields, "author")}
        await self.session.execute(
            statement.on_conflict_do_update(
                index_elements=["org", "agent", "name"], set_={**replaced, "set_at": func.now()}
            )
        )

    async def drop(self, org: str, agent: str, name: str) -> bool:
        """Forget one of the agent's callers; whether it was there."""
        statement = delete(AgentPersona).where(
            AgentPersona.org == org, AgentPersona.agent == agent, AgentPersona.name == name
        )
        return await self.changed(statement) > 0


class PersonaSwitchRepository(Repository[PersonaSwitch]):
    """Which of the library's personas an agent's runs play, and on what model and voice."""

    model = PersonaSwitch

    # The agent's own row after the org's, so it wins when both switched the same persona.
    async def for_agent(self, org: str, agent: str) -> Sequence[PersonaSwitch]:
        """The org's rows, then the agent's, for every library persona either touched."""
        statement = (
            self.statement()
            .where(PersonaSwitch.org == org, PersonaSwitch.agent.in_([THE_ORGS_OWN, agent]))
            .order_by(PersonaSwitch.agent)
        )
        return await self.all(statement)

    async def switch(self, org: str, agent: str, names: Sequence[str], *, on: bool, author: str) -> None:
        """Turn library personas on or off, for the org (agent '') or for one agent."""
        for name in names:
            statement = upsert(PersonaSwitch).values(org=org, agent=agent, name=name, is_on=on, author=author)
            replaced = {"is_on": statement.excluded.is_on, "author": statement.excluded.author, "set_at": func.now()}
            await self.session.execute(
                statement.on_conflict_do_update(index_elements=["org", "agent", "name"], set_=replaced)
            )

    # A new row takes the switch the persona has now; an existing one keeps its switch.
    async def play(
        self,
        org: str,
        agent: str,
        name: str,
        *,
        is_on: bool,
        llm: str | None,
        tts: str | None,
        voice: str | None,
        author: str,
    ) -> None:
        """Set how one of the library's personas is played for the agent, every field at once."""
        statement = upsert(PersonaSwitch).values(
            org=org, agent=agent, name=name, is_on=is_on, llm=llm, tts=tts, voice=voice, author=author
        )
        replaced = {
            "llm": statement.excluded.llm,
            "tts": statement.excluded.tts,
            "voice": statement.excluded.voice,
            "author": statement.excluded.author,
            "set_at": func.now(),
        }
        await self.session.execute(
            statement.on_conflict_do_update(index_elements=["org", "agent", "name"], set_=replaced)
        )
