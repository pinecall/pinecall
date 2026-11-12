"""Which of the library's judges and personas run: the org's row, an agent's that wins over it, how one is played."""

from collections.abc import Sequence

from sqlalchemy import func
from sqlalchemy.dialects.postgresql import insert as upsert

from runtime.actor import THE_ORGS_OWN
from runtime.judging.models import JudgeSwitch, PersonaSwitch
from runtime.kit.repository import Repository


# `judge_switches` and `persona_switches` are one table twice, the second with how a persona is
# played beside its switch. Until 2026-11 each had its own repository, the two `switch` alike to the letter.
class SwitchRepository[M: (JudgeSwitch, PersonaSwitch)](Repository[M]):
    """The switches of one library: the org's rows (agent '') and each agent's own."""

    # The agent's own row after the org's, so it wins when both switched the same name.
    async def list_for_agent(self, org: str, agent: str) -> Sequence[M]:
        """The org's rows, then the agent's, for every name of the library either touched."""
        levels = self.model.agent.in_([THE_ORGS_OWN, agent])
        return await self.all(self.statement().where(self.model.org == org, levels).order_by(self.model.agent))

    async def switch(self, org: str, agent: str, names: Sequence[str], *, on: bool, author: str) -> None:
        """Turn names of the library on or off, for the org (agent '') or for one agent."""
        for name in names:
            statement = upsert(self.model).values(org=org, agent=agent, name=name, is_on=on, author=author)
            replaced = {"is_on": statement.excluded.is_on, "author": statement.excluded.author, "set_at": func.now()}
            await self.session.execute(
                statement.on_conflict_do_update(index_elements=["org", "agent", "name"], set_=replaced)
            )


class JudgeSwitchRepository(SwitchRepository[JudgeSwitch]):
    """Which of the library's judges run."""

    model = JudgeSwitch


class PersonaSwitchRepository(SwitchRepository[PersonaSwitch]):
    """Which of the library's personas an agent's runs play, and on what model and voice."""

    model = PersonaSwitch

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
