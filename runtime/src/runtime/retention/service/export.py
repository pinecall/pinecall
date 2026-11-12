"""An org's env as JSON Lines: a header, its calls, then every table that declares what an export carries."""

import json
from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from runtime.calls import service as calls
from runtime.enums import Env
from runtime.kit.time import epoch
from runtime.postgres import without_timeouts
from runtime.retention.repository.export import ExportRepository


# A session of its own: the export streams after the endpoint returned and its session closed. Every
# read is of the whole org, so no statement of it is timed out; each table is read as a stream, never
# held whole.
async def export_lines(sessions: async_sessionmaker[AsyncSession], org: str, env: Env) -> AsyncIterator[str]:
    """Every line: the header, the calls with their logs, then each exported table's rows."""
    yield json.dumps({"kind": "export", "org": org, "env": env.value, "exported_at": epoch()})
    async with sessions() as session, without_timeouts(session):
        async for line in calls.export_calls(session, org, env):
            yield line
        async for line in ExportRepository(session).stream_lines(org, env):
            yield line
