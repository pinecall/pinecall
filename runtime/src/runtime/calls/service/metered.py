"""The metered feed over every log: a page of what was consumed after a cursor, its totals, and the feed followed."""

from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from runtime.accounts import service as accounts
from runtime.calls.folds.usage import Usage, UsageRow, bill_row, total_by_org, usage_row
from runtime.calls.log.feeds import Feeds
from runtime.calls.log.writer import METERED_TYPES
from runtime.calls.repository.entries import A_PAGE, EntryRepository
from runtime.calls.repository.facts import FactsRepository
from runtime.calls.repository.spend import SpendRepository
from runtime.scoping import box_wide

SUMMARY = "call.summary"


@dataclass(frozen=True, slots=True)
class MeteredPage:
    """One page of the usage feed: the rows kept, and the cursor past everything read."""

    rows: list[UsageRow]
    next: int | None


@dataclass(frozen=True, slots=True)
class OrgUsage:
    """An org's metered rows after a cursor, what they add up to, and the next cursor."""

    rows: list[UsageRow]
    totals: Usage | None
    next: int | None


@dataclass(frozen=True, slots=True)
class BoxUsage:
    """Every org's metered rows after a cursor, what they add up to per org, and the next cursor."""

    rows: list[UsageRow]
    totals: dict[str, Usage]
    next: int | None


# The cursor is the store's position of the last row read: a billing consumer resumes from it and
# counts nothing twice. It moves past every row read, kept or not, so a page filtered to one org
# still moves. A summary's row carries what its facts keep of it: the vendors its call ran on the
# box's keys, and its simulated caller's cost. The rows are read on the session given: until 2026-11
# they were asked of the store, on a second connection.
async def read_page(session: AsyncSession, *, after: int, limit: int, org: str | None) -> MeteredPage:
    """The metered rows after the cursor, of one org or of every org, each folded and billed."""
    found = await EntryRepository(session).list_across(METERED_TYPES, after=after, limit=limit)
    read = [usage_row(item) for item in found]
    kept = [row for row in read if org is None or row.org == org]
    return MeteredPage(rows=await _bill(session, kept), next=read[-1].cursor if read else None)


async def usage_of(session: AsyncSession, org: str, *, after: int, limit: int) -> OrgUsage:
    """The org's metered rows after the cursor, their totals, and the next cursor."""
    page = await read_page(session, after=after, limit=limit, org=org)
    return OrgUsage(rows=page.rows, totals=total_by_org(page.rows).get(org), next=page.next)


async def box_usage_of(session: AsyncSession, named: str | None, *, after: int, limit: int) -> BoxUsage:
    """Every org's metered rows after the cursor, or one org's when named (its slug or its id), totals per org."""
    page = await read_page(session, after=after, limit=limit, org=await find_named(session, named))
    return BoxUsage(rows=page.rows, totals=total_by_org(page.rows), next=page.next)


async def find_named(session: AsyncSession, named: str | None) -> str | None:
    """The id of the org an operator named by slug or id; the word itself for one that is no org's, None for none."""
    if named is None:
        return None
    found = await accounts.find_org(session, named)
    return named if found is None else found.id


# The rows are read from the cursor now, and again each time a gateway says one was written: the
# reader is subscribed first, so a row written between the two is heard and read. Each page is read
# on a session of its own, the box's: a stream outlives the request's.
async def follow_metered(
    feeds: Feeds, sessions: async_sessionmaker[AsyncSession], *, after: int, org: str | None
) -> AsyncIterator[UsageRow]:
    """The metered rows after the cursor, then each as it is written, for as long as the reader stays."""
    heard = await feeds.usage_reader()
    cursor = after
    try:
        reading = True
        while reading:
            page = await _read_box_wide(sessions, cursor, org)
            for row in page.rows:
                yield row
            if page.next is not None:
                cursor = page.next
                continue
            reading = await anext(heard, None) is not None
    finally:
        heard.close()


async def _read_box_wide(sessions: async_sessionmaker[AsyncSession], after: int, org: str | None) -> MeteredPage:
    with box_wide():
        async with sessions() as session:
            return await read_page(session, after=after, limit=A_PAGE, org=org)


# Not in the summary: the gateway keeps both with the call's facts (the lent vendors at the seal,
# the caller's cost when the simulation ends), and the log's wire stays the one every SDK reads.
async def _bill(session: AsyncSession, rows: list[UsageRow]) -> list[UsageRow]:
    calls = [row.call for row in rows if row.type == SUMMARY and row.call]
    if not calls:
        return rows
    with box_wide():
        billed = await FactsRepository(session).list_billed(calls)
    return [
        bill_row(row, billed[row.call].lent, billed[row.call].caller_cost_usd)
        if row.type == SUMMARY and row.call in billed
        else row
        for row in rows
    ]


# ── what the seal keeps and asks of the dollars ──


# No entry says it: the worker tells the seal which vendors ran on the box's own key, and the
# operator bills their usage off the row.
async def keep_lent(session: AsyncSession, call: str, vendors: Sequence[str]) -> None:
    """Keep the vendors the call ran on the box's own key with its facts."""
    await FactsRepository(session).keep(call, lent=list(vendors))


# What alerts' watch of an org's spend is handed (`alerts.service.spend.SpendByDay`).
async def sum_spend_by_day(session: AsyncSession, org: str, day: float, since: float) -> tuple[float, float]:
    """The org's dollars since the day started, and those from `since` to its start."""
    return await SpendRepository(session).sum_today_and_before(org, day, since)
