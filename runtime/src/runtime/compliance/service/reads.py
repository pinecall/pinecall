"""Who read what: every read of an org's calls, recordings, exports and memory written down, and listed."""

import logging
from collections.abc import Sequence

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from runtime.actor import Scope
from runtime.compliance.models import Read
from runtime.compliance.repository.reads import ReadRepository
from runtime.enums import ReadKind

logger = logging.getLogger(__name__)

# Who reads, or erases, on the box's own behalf: off the box, or through its own endpoints.
OPERATOR = "operator"


# A record that cannot be written is said in the log and the read goes on: an audit that fails a
# read would be a way to stop every read. The savepoint keeps the session usable after it.
async def record_read(session: AsyncSession, scope: Scope, subject: str, what: ReadKind, *, by: str) -> None:
    """Write down who read the subject, and what of it; once an hour per reader."""
    try:
        async with session.begin_nested():
            await ReadRepository(session).record(scope.org, scope.env, subject, what, by)
    except SQLAlchemyError:
        logger.warning("the read of %s by %s went unrecorded; the read goes on", subject, by, exc_info=True)


async def list_reads(session: AsyncSession, scope: Scope, *, subject: str | None = None) -> Sequence[Read]:
    """The reads in the scope's env, newest first, of one call or number when named."""
    return await ReadRepository(session).list_of_env(scope.org, scope.env, subject=subject)
