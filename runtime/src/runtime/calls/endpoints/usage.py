"""The usage feed: the org's metered rows after a cursor, and every org's for the operator, as pages or a stream."""

from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import APIRouter, Query, Request
from fastapi.responses import StreamingResponse

from runtime.auth import TheOperator
from runtime.calls import schemas
from runtime.calls.auth import TheFeeds, UsageKey
from runtime.calls.folds import usage as folded
from runtime.calls.service import metered
from runtime.handles import TheClosing, TheSessions
from runtime.kit import sse
from runtime.postgres import Session, TheBoxSession

router = APIRouter()

RETRY_MS = 1000


# The cursor is the store's position of the last row read: a billing consumer resumes from it and
# counts nothing twice.
@router.get("/v1/usage")
async def usage_feed(
    actor: UsageKey, session: Session, query: Annotated[schemas.UsageQuery, Query()]
) -> schemas.UsagePage:
    """The org's metered rows after the cursor, their totals, and the next cursor."""
    return schemas.UsagePage.of(await metered.usage_of(session, actor.org, after=query.after, limit=query.limit))


@router.get("/v1/ops/usage", response_model=None)
async def box_usage(
    _actor: TheOperator,
    request: Request,
    feeds: TheFeeds,
    sessions: TheSessions,
    session: TheBoxSession,
    closing: TheClosing,
    query: Annotated[schemas.BoxUsageQuery, Query()],
) -> StreamingResponse | schemas.BoxUsagePage:
    """Every org's metered rows after the cursor, totals per org; or the same as a stream."""
    if sse.wants_sse(request):
        only = await metered.find_named(session, query.org)
        rows = metered.follow_metered(feeds, sessions, after=query.after, org=only)
        return sse.stream(sse.pace(_frames(rows), closing=closing))
    found = await metered.box_usage_of(session, query.org, after=query.after, limit=query.limit)
    return schemas.BoxUsagePage.of(found)


async def _frames(rows: AsyncIterator[folded.UsageRow]) -> AsyncIterator[str]:
    yield f"retry: {RETRY_MS}\n\n"
    async for row in rows:
        yield sse.frame(schemas.UsageRow.of(row).model_dump_json(), event="usage", id_=str(row.cursor))
