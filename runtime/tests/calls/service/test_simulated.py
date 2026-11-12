"""A simulated caller's call: who played it is kept with its facts, and it is on the line until it is summed up."""

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from runtime.actor import Scope
from runtime.calls.log.store import Store
from runtime.calls.models import CallFact
from runtime.calls.repository.heads import Claim
from runtime.calls.service import simulated
from runtime.enums import Env
from runtime.kit.text import JsonObject
from tests.calls.factories import CALLER, LINE, a_summary, claim_call
from tests.conftest import Tenant, needs_the_database

pytestmark = needs_the_database

GEMINI = "google/gemini-3.5-flash-lite"


async def test_who_played_a_simulated_caller_is_kept_with_its_facts_and_kept_again_as_the_last_said(
    sessions: async_sessionmaker[AsyncSession], call: str
) -> None:
    """A run that names another voice writes over the first: the facts say who played the caller last."""
    async with sessions.begin() as session:
        await simulated.keep_caller_played(session, call, llm="google/gemini-3.5-flash-lite", tts=None, voice=None)
        await simulated.keep_caller_played(
            session, call, llm="google/gemini-3.5-flash-lite", tts="google", voice="Puck"
        )
    async with sessions() as session:
        kept = await session.get(CallFact, call)
    assert kept is not None
    assert (kept.caller_llm, kept.caller_tts, kept.caller_voice) == (GEMINI, "google", "Puck")


# A call these tests begin says it started a second into the epoch: asked ten seconds in, it began within the hour.
NOW = 10.0


async def begun(store: Store, tenant: Tenant, agent: str, call: str, *, persona: str | None) -> None:
    """A call of the tenant's sandbox that has started, as a simulated caller's when it names a persona."""
    await claim_call(store, call, agent, Claim(Scope(tenant.org, Env.sandbox)))
    started: JsonObject = {**LINE, "direction": "inbound", "caller": CALLER, "started_at": 1.0}
    if persona is not None:
        started["persona"] = persona
    await store.write("entry", call, agent, "call.started", started)
    await store.writer.drain()


async def on_the_line(sessions: async_sessionmaker[AsyncSession], tenant: Tenant, env: Env = Env.sandbox) -> int:
    async with sessions() as session:
        return await simulated.count_simulating(session, tenant.org, env, at=NOW)


async def test_a_simulated_call_that_began_counts_as_one_on_the_line_until_its_summary_is_written(
    store: Store, sessions: async_sessionmaker[AsyncSession], tenant: Tenant, call: str, agent: str
) -> None:
    """H F3: the meter counts a simulation when its call ends, and a burst begun before any ended passed the limit."""
    await begun(store, tenant, agent, f"{call}-sim", persona="in-a-hurry")
    await begun(store, tenant, agent, f"{call}-person", persona=None)
    assert await on_the_line(sessions, tenant) == 1
    assert await on_the_line(sessions, tenant, Env.production) == 0
    await store.write("entry", f"{call}-sim", agent, "call.summary", {**a_summary([]), "simulated": True})
    await store.writer.drain()
    assert await on_the_line(sessions, tenant) == 0
