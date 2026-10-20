"""The usage feed's page: a summary carries the vendors its call ran on the box's own key and its simulated
caller's cost, both kept with its facts."""

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from pinecall_runtime.calls.metering import UsageRow
from pinecall_runtime.calls.repository.facts import FactsRepository
from pinecall_runtime.calls.service import usage
from pinecall_runtime.calls.store import Store
from pinecall_runtime.kit.text import JsonObject
from tests.calls.factories import a_summary
from tests.conftest import needs_the_database

pytestmark = needs_the_database

STT: JsonObject = {"type": "stt_usage", "provider": "deepgram", "model": "flux", "audio_duration": 118.0}


# Every test shares the database: the feed is read whole, and the rows kept are this test's calls.
async def summaries_of(store: Store, sessions: async_sessionmaker[AsyncSession], calls: set[str]) -> list[UsageRow]:
    found: list[UsageRow] = []
    after = 0
    while True:
        async with sessions() as session:
            page = await usage.metered_page(store, session, after=after, limit=500, org=None)
        found += [row for row in page.rows if row.call in calls and row.type == "call.summary"]
        if page.next is None:
            return found
        after = page.next


async def test_a_summary_carries_the_vendors_its_call_ran_on_the_boxs_key_and_one_on_its_own_keys_none(
    store: Store, sessions: async_sessionmaker[AsyncSession], call: str, agent: str
) -> None:
    """The facts keep the lent vendors at the seal; the feed reads them onto the call's summary."""
    own = f"{call}-own"
    await store.append(call, agent, "call.summary", a_summary([STT]), ephemeral=False)
    await store.append(own, agent, "call.summary", a_summary([STT]), ephemeral=False)
    await store.writer.drain()
    async with sessions.begin() as session:
        await FactsRepository(session).set_lent(call, ["deepgram", "google"])
    rows = {row.call: row for row in await summaries_of(store, sessions, {call, own})}
    assert (rows[call].lent, rows[call].used.lent_minutes) == (("deepgram", "google"), 2.0)
    assert (rows[own].lent, rows[own].used.lent_minutes) == ((), 0.0)


async def test_a_simulations_caller_cost_is_added_line_by_line_and_read_onto_its_summary(
    store: Store, sessions: async_sessionmaker[AsyncSession], call: str, agent: str
) -> None:
    """Each simulation that ends adds what its caller spent; the feed reads the sum onto the call's summary."""
    await store.append(call, agent, "call.summary", {**a_summary([STT]), "simulated": True}, ephemeral=False)
    await store.writer.drain()
    async with sessions.begin() as session:
        await usage.keep_caller_cost(session, call, 0.004)
        await usage.keep_caller_cost(session, call, 0.002)
        await usage.keep_caller_cost(session, call, 0.0)
    (row,) = await summaries_of(store, sessions, {call})
    assert (row.lent, round(row.used.caller_cost_usd, 6), row.used.simulations) == ((), 0.006, 1)
