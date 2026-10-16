"""The judges an org writes, the org's (agent '') and one agent's own, and the library's switches."""

from collections.abc import Sequence

from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert as upsert

from pinecall_runtime.enums import JudgeAnswer, JudgeRunsWhen
from pinecall_runtime.judging.models import AgentJudge, JudgeSwitch
from pinecall_runtime.kit.auth import THE_ORGS_OWN
from pinecall_runtime.kit.repository import Repository


class JudgeRepository(Repository[AgentJudge]):
    """One row per org, level (the org's is agent '') and name."""

    model = AgentJudge

    async def at_level(self, org: str, agent: str) -> Sequence[AgentJudge]:
        """The judges written at one level, the org's or an agent's own, by name."""
        statement = self.statement().where(AgentJudge.org == org, AgentJudge.agent == agent).order_by(AgentJudge.name)
        return await self.all(statement)

    # The org's rows first: their agent is '', which sorts before any slug.
    async def for_call(self, org: str, agent: str) -> Sequence[AgentJudge]:
        """Every judge a call of the agent is held to: the org's, then its own."""
        statement = (
            self.statement()
            .where(AgentJudge.org == org, AgentJudge.agent.in_([THE_ORGS_OWN, agent]))
            .order_by(AgentJudge.agent, AgentJudge.name)
        )
        return await self.all(statement)

    # A name is one question per call: the org's and an agent's may not share it, since a call of
    # that agent would carry two verdicts under one name. Two agents may.
    async def clashing(self, org: str, agent: str, name: str) -> str | None:
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

    async def put(
        self,
        org: str,
        agent: str,
        *,
        name: str,
        question: str,
        answer: JudgeAnswer,
        choices: Sequence[str],
        runs_when: JudgeRunsWhen,
        trigger: str,
        reads: Sequence[str],
        author: str,
    ) -> None:
        """Write a judge whole; the same name again replaces it."""
        values = {
            "org": org,
            "agent": agent,
            "name": name,
            "question": question,
            "answer": answer,
            "choices": list(choices),
            "runs_when": runs_when,
            "trigger": trigger,
            "reads": list(reads),
            "author": author,
        }
        statement = upsert(AgentJudge).values(**values)
        replaced = {
            key: statement.excluded[key]
            for key in ("question", "answer", "choices", "runs_when", "trigger", "reads", "author")
        }
        await self.session.execute(
            statement.on_conflict_do_update(
                index_elements=["org", "agent", "name"], set_={**replaced, "set_at": func.now()}
            )
        )

    async def drop(self, org: str, agent: str, name: str) -> bool:
        """Forget a judge at one level; whether it was there."""
        statement = delete(AgentJudge).where(AgentJudge.org == org, AgentJudge.agent == agent, AgentJudge.name == name)
        return await self.changed(statement) > 0


class JudgeSwitchRepository(Repository[JudgeSwitch]):
    """Which of the library's judges run: the org's row, and an agent's that wins over it."""

    model = JudgeSwitch

    # The agent's own row after the org's, so it wins when both switched the same judge.
    async def for_agent(self, org: str, agent: str) -> dict[str, bool]:
        """Which of the library's judges the agent's calls run, as the org and the agent set them."""
        statement = (
            self.statement()
            .where(JudgeSwitch.org == org, JudgeSwitch.agent.in_([THE_ORGS_OWN, agent]))
            .order_by(JudgeSwitch.agent)
        )
        return {row.name: row.is_on for row in await self.all(statement)}

    async def at_level(self, org: str, agent: str) -> dict[str, bool]:
        """The switches written at one level alone: the org's (agent '') or an agent's own."""
        statement = self.statement().where(JudgeSwitch.org == org, JudgeSwitch.agent == agent)
        return {row.name: row.is_on for row in await self.all(statement)}

    async def switch(self, org: str, agent: str, names: Sequence[str], *, on: bool, author: str) -> None:
        """Turn library judges on or off, for the org (agent '') or for one agent."""
        for name in names:
            statement = upsert(JudgeSwitch).values(org=org, agent=agent, name=name, is_on=on, author=author)
            replaced = {"is_on": statement.excluded.is_on, "author": statement.excluded.author, "set_at": func.now()}
            await self.session.execute(
                statement.on_conflict_do_update(index_elements=["org", "agent", "name"], set_=replaced)
            )
