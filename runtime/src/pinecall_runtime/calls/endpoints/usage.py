"""The usage feed: the org's metered rows after a cursor, every org's for the operator, and the box's floor."""

from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import APIRouter, Query, Request
from fastapi.responses import StreamingResponse

from pinecall_runtime.accounts.service import orgs
from pinecall_runtime.calls import schemas
from pinecall_runtime.calls.auth import TheOperator, TheServing, UsageKey
from pinecall_runtime.calls.metering import Usage, UsageRow, totals_by_org
from pinecall_runtime.calls.service import usage
from pinecall_runtime.calls.service.serving import Serving
from pinecall_runtime.kit import sse
from pinecall_runtime.postgres import Session, box_wide
from pinecall_runtime.wire.base import Entry

router = APIRouter()

RETRY_MS = 1000
# What the box says of itself belongs to no org and is sent whole; any other entry whose log
# nobody claimed yet carries no org, and is left out.
BOX_OWN = frozenset({"worker.changed"})


# The cursor is the store's position of the last row read: a billing consumer resumes from it and
# counts nothing twice.
@router.get("/v1/usage")
async def usage_feed(
    actor: UsageKey, serving: TheServing, session: Session, query: Annotated[schemas.UsageQuery, Query()]
) -> schemas.UsagePage:
    """The org's metered rows after the cursor, their totals, and the next cursor."""
    page = await usage.metered_page(serving.logs.store, session, after=query.after, limit=query.limit, org=actor.org)
    totals = totals_by_org(page.rows).get(actor.org)
    return schemas.UsagePage(
        rows=[usage_row(row) for row in page.rows],
        totals=None if totals is None else usage_totals(totals),
        next=page.next,
    )


@router.get("/v1/ops/usage", response_model=None)
async def box_usage(
    _actor: TheOperator,
    request: Request,
    serving: TheServing,
    session: Session,
    query: Annotated[schemas.BoxUsageQuery, Query()],
) -> StreamingResponse | schemas.BoxUsagePage:
    """Every org's metered rows after the cursor, totals per org; or the same as a stream."""
    only = None
    if query.org is not None:
        with box_wide():
            found = await orgs.find_org(session, query.org)
        only = query.org if found is None else found.id
    if sse.wants_sse(request):
        frames = _metered_stream(serving, query.after, only)
        return sse.streamed(sse.paced(frames, closing=request.app.state.closing))
    page = await usage.metered_page(serving.logs.store, session, after=query.after, limit=query.limit, org=only)
    return schemas.BoxUsagePage(
        rows=[usage_row(row) for row in page.rows],
        totals={named: usage_totals(used) for named, used in totals_by_org(page.rows).items()},
        next=page.next,
    )


# Live only, no cursor: frame ids are per-log seqs that interleave, so a reconnect starts now.
@router.get("/v1/ops/events", response_model=None)
async def stream_box_events(_actor: TheOperator, request: Request, serving: TheServing) -> StreamingResponse:
    """Every org's floor at once, each frame saying whose."""
    entries = await serving.logs.box_reader()
    return sse.streamed(sse.paced(_owned(serving, entries), closing=request.app.state.closing))


def usage_row(row: UsageRow) -> schemas.UsageRow:
    """A folded row as the feed sends it."""
    used = row.used
    return schemas.UsageRow(
        cursor=row.cursor,
        org=row.org,
        agent=row.agent,
        call=row.call,
        type=row.type,
        at=row.at,
        minutes=used.minutes,
        messages=used.messages,
        input_tokens=used.input_tokens,
        output_tokens=used.output_tokens,
        characters=used.characters,
        judge_calls=used.judge_calls,
        evals=used.evals,
        simulated=used.simulations > 0,
        cost_usd=used.cost_usd,
        lent=list(row.lent),
    )


def usage_totals(used: Usage) -> schemas.UsageTotals:
    """A sum of usage as the feed sends it."""
    return schemas.UsageTotals(
        calls=used.calls,
        minutes=used.minutes,
        messages=used.messages,
        input_tokens=used.input_tokens,
        output_tokens=used.output_tokens,
        characters=used.characters,
        judge_calls=used.judge_calls,
        evals=used.evals,
        simulations=used.simulations,
        cost_usd=used.cost_usd,
        lent_minutes=used.lent_minutes,
    )


async def _owned(serving: Serving, entries: AsyncIterator[Entry]) -> AsyncIterator[str]:
    yield f"retry: {RETRY_MS}\n\n"
    async for entry in entries:
        if entry.type in BOX_OWN:
            event = schemas.BoxEvent(org="", entry=entry)
        else:
            claimant = await serving.logs.claimant_of(entry)
            if claimant is None:
                continue
            event = schemas.BoxEvent(org=claimant.org, env=claimant.env, entry=entry)
        yield sse.frame(event.dump_json(), event=entry.type, id_=str(entry.seq))


# The rows are read from the cursor now, and again each time a gateway says one was written: the
# reader is subscribed first, so a row written between the two is heard and read.
async def _metered_stream(serving: Serving, after: int, only: str | None) -> AsyncIterator[str]:
    yield f"retry: {RETRY_MS}\n\n"
    heard = await serving.logs.metered_reader()
    cursor = after
    try:
        while True:
            while True:
                async with serving.handles.sessions() as session:
                    page = await usage.metered_page(
                        serving.logs.store, session, after=cursor, limit=schemas.DEFAULT_LIMIT, org=only
                    )
                for row in page.rows:
                    yield sse.frame(usage_row(row).dump_json(), event="usage", id_=str(row.cursor))
                if page.next is None:
                    break
                cursor = page.next
            if await anext(heard, None) is None:
                return
    finally:
        heard.close()
