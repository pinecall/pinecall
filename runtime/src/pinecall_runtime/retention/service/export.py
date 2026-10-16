"""An org's env as JSON Lines: calls, memories, settings, lexicon, documents, consent, drift."""

import json
from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncSession

from pinecall_runtime.enums import Env
from pinecall_runtime.kit.time import epoch
from pinecall_runtime.postgres import unbounded
from pinecall_runtime.retention.repository import ExportRepository
from pinecall_runtime.retention.repository.export import AFTER_THE_CALLS

A_PAGE_OF_CALLS = 100


async def export_lines(session: AsyncSession, org: str, env: Env) -> AsyncIterator[str]:
    """Every line: the header, the calls, then memories, settings, lexicon, documents, consent, drift."""
    repository = ExportRepository(session)
    yield json.dumps({"kind": "export", "org": org, "env": env.value, "exported_at": epoch()})
    async with unbounded(session):
        at, call = -1.0, ""
        while True:
            rows = await repository.calls_after(org, env, at, call, page=A_PAGE_OF_CALLS)
            for row in rows:
                yield str(row.line)
            if len(rows) < A_PAGE_OF_CALLS:
                break
            at, call = float(rows[-1].at), str(rows[-1].call)
        for query in AFTER_THE_CALLS:
            for line in await repository.lines_of(query, org, env):
                yield line
