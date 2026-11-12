"""An org's calls as an export carries them: a line a call, its facts and its whole log in it."""

from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncSession

from runtime.calls.repository.export import CallExportRepository
from runtime.enums import Env

A_PAGE_OF_CALLS = 100


# A page at a time, by the key of the last line read: an org of any size is exported in bounded memory.
async def export_calls(session: AsyncSession, org: str, env: Env) -> AsyncIterator[str]:
    """Every call of the org in the env, oldest first, each as its JSON line."""
    repository = CallExportRepository(session)
    at, call, more = -1.0, "", True
    while more:
        rows = await repository.list_after(org, env, at, call, page=A_PAGE_OF_CALLS)
        for row in rows:
            yield row.line
        more = len(rows) == A_PAGE_OF_CALLS
        if rows:
            at, call = rows[-1].at, rows[-1].call
