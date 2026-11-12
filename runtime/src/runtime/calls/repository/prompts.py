"""The prompts rows: each block of prompt an org's calls were told, by its hash."""

from collections.abc import Sequence

from sqlalchemy.dialects.postgresql import insert

from runtime.calls.models import Prompt
from runtime.kit.repository import Repository


class PromptRepository(Repository[Prompt]):
    """The blocks of prompt an org's calls were told, by hash."""

    model = Prompt

    # One statement: until 2026-11 it looked and then inserted, and two gateways keeping the same
    # block at once broke the second one's transaction on the key.
    async def keep(self, org: str, hashed: str, text: str) -> None:
        """Keep the text under its hash, once; one kept already stays."""
        statement = insert(Prompt).values(org=org, hash=hashed, text=text)
        await self.session.execute(statement.on_conflict_do_nothing(index_elements=[Prompt.org, Prompt.hash]))

    async def texts_of(self, org: str, hashes: Sequence[str]) -> dict[str, str]:
        """The org's texts of these hashes, those it kept."""
        if not hashes:
            return {}
        rows = await self.all(self.statement().where(Prompt.org == org, Prompt.hash.in_(hashes)))
        return {row.hash: row.text for row in rows}
