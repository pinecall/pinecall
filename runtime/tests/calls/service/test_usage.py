"""The usage feed's page: a summary carries the vendors its call ran on the box's own key and its simulated
caller's cost, both kept with its facts."""

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from pinecall_runtime.calls.metering import UsageRow
from pinecall_runtime.calls.models import CallFact
from pinecall_runtime.calls.repository.facts import FactsRepository
from pinecall_runtime.calls.repository.heads import Claim
from pinecall_runtime.calls.service import usage
from pinecall_runtime.calls.store import Store
from pinecall_runtime.enums import Env
from pinecall_runtime.kit.auth import Scope
from pinecall_runtime.kit.text import JsonObject
from tests.calls.factories import CALLER, LINE, a_summary
from tests.conftest import Tenant, needs_the_database

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


async def test_who_played_a_simulated_caller_is_kept_with_its_facts_and_kept_again_as_the_last_said(
    sessions: async_sessionmaker[AsyncSession], call: str
) -> None:
    """A run that names another voice writes over the first: the facts say who played the caller last."""
    async with sessions.begin() as session:
        await usage.keep_caller_played(session, call, llm="google/gemini-3.5-flash-lite", tts=None, voice=None)
        await usage.keep_caller_played(session, call, llm="google/gemini-3.5-flash-lite", tts="google", voice="Puck")
    async with sessions() as session:
        kept = await session.get(CallFact, call)
    assert kept is not None
    assert (kept.caller_llm, kept.caller_tts, kept.caller_voice) == ("google/gemini-3.5-flash-lite", "google", "Puck")


# The store's clock ticks from 1.0, so a call these tests begin started a second or two into the epoch.
NOW = 10.0


async def begun(store: Store, tenant: Tenant, agent: str, call: str, *, persona: str | None) -> None:
    """A call of the tenant's sandbox that has started, as a simulated caller's when it names a persona."""
    await store.claim(call, agent, tenant.org, Claim(Scope(tenant.org, Env.sandbox)))
    started: JsonObject = {**LINE, "direction": "inbound", "caller": CALLER, "started_at": 1.0}
    if persona is not None:
        started["persona"] = persona
    await store.append(call, agent, "call.started", started, ephemeral=False)
    await store.writer.drain()


async def on_the_line(sessions: async_sessionmaker[AsyncSession], tenant: Tenant, env: Env = Env.sandbox) -> int:
    async with sessions() as session:
        return await usage.simulating(session, tenant.org, env, at=NOW)


async def test_a_simulated_call_that_began_counts_as_one_on_the_line_until_its_summary_is_written(
    store: Store, sessions: async_sessionmaker[AsyncSession], tenant: Tenant, call: str, agent: str
) -> None:
    """H F3: the meter counts a simulation when its call ends, and a burst begun before any ended passed the limit."""
    await begun(store, tenant, agent, f"{call}-sim", persona="in-a-hurry")
    await begun(store, tenant, agent, f"{call}-person", persona=None)
    assert await on_the_line(sessions, tenant) == 1
    assert await on_the_line(sessions, tenant, Env.production) == 0
    await store.append(f"{call}-sim", agent, "call.summary", {**a_summary([]), "simulated": True}, ephemeral=False)
    await store.writer.drain()
    assert await on_the_line(sessions, tenant) == 0
