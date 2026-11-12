"""An erasure's statements: the trail, and the rows of every table that declares a call, an agent or a contact."""

from collections.abc import Sequence

from sqlalchemy import Table, delete

from runtime.enums import Env
from runtime.kit.db import Kept, list_kept
from runtime.kit.repository import Repository
from runtime.retention.models import Erasure

A_TRAIL_PAGE = 100
# The column a log is named by, where a table names its call by its log.
BY_LOG = "log"


# No table is named here: each model says, in its own file, which column names the call, the agent
# and the contact a row is of (`Kept`), and this walks what is declared. A table that says it outlives
# an erasure is left. Until 2026-11 the deletes were three lists kept by hand in this module, and a
# table a domain added was erased by none of them: five tables outlived their agent.
class ErasureRepository(Repository[Erasure]):
    """The trail of the org's erasures, and the deletes an erasure makes of what every table declares."""

    model = Erasure

    async def list_trail(self, org: str, *, limit: int = A_TRAIL_PAGE) -> Sequence[Erasure]:
        """The org's erasures, newest first."""
        statement = (
            self.statement().where(Erasure.org == org).order_by(Erasure.at.desc(), Erasure.id.desc()).limit(limit)
        )
        return await self.all(statement)

    # A row names its call by the call's id, or by its log, which a call's id is too: both are handed.
    async def delete_of_calls(self, logs: Sequence[str], calls: Sequence[str]) -> int:
        """Delete every row a table declares as one of these calls'; how many went."""
        deleted = 0
        for table, kept in _list_declaring():
            if kept.call is not None:
                named = logs if kept.call == BY_LOG else calls
                deleted += await self.change(delete(table).where(table.c[kept.call].in_(named)))
        return deleted

    async def delete_of_agent(self, org: str, agent: str) -> int:
        """Delete every row a table of the org declares as this agent's, in both envs; how many went."""
        deleted = 0
        for table, kept in _list_declaring():
            if kept.agent is not None and "org" in table.c:
                statement = delete(table).where(table.c.org == org, table.c[kept.agent] == agent)
                deleted += await self.change(statement)
        return deleted

    async def delete_of_contact(self, org: str, env: Env, contact: str) -> int:
        """Delete every row a table of the org declares as this contact's in the env; how many went."""
        deleted = 0
        for table, kept in _list_declaring():
            if kept.contact is not None and "org" in table.c and "env" in table.c:
                statement = delete(table).where(
                    table.c.org == org, table.c.env == env, table.c[kept.contact] == contact
                )
                deleted += await self.change(statement)
        return deleted


# What every table declares, the ones that say they outlive an erasure left out.
def _list_declaring() -> list[tuple[Table, Kept]]:
    return [(table, kept) for table, kept in list_kept() if not kept.outlives]
