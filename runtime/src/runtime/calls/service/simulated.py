"""What a simulated call keeps beside its fold: who played its caller, what that cost, how it was heard."""

from collections.abc import Mapping
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from runtime.calls.repository.facts import FactsRepository
from runtime.enums import Env
from runtime.wire.room import A_SIMULATED_CALLER

# A simulated call plays a quarter of an hour at most, and is summed up a moment after it ends.
A_SIMULATION_MAY_BE_ON_THE_LINE_S = 60 * 60.0


async def count_simulating(session: AsyncSession, org: str, env: Env, *, at: float) -> int:
    """The simulated calls of the org in the env that began and are not yet summed up: not in its usage yet."""
    since = at - A_SIMULATION_MAY_BE_ON_THE_LINE_S
    return await FactsRepository(session).count_simulating(org, env, since, A_SIMULATED_CALLER)


async def add_caller_cost(session: AsyncSession, call: str, usd: float) -> None:
    """Add what a simulated caller's own model and voice cost to the call's facts, for the feed."""
    if usd > 0:
        await FactsRepository(session).add_caller_cost(call, usd)


async def keep_caller_played(session: AsyncSession, call: str, *, llm: str, tts: str | None, voice: str | None) -> None:
    """Keep who plays a simulated caller with the call's facts: its lines' model, its voice's, the voice."""
    await FactsRepository(session).keep(call, caller_llm=llm, caller_tts=tts, caller_voice=voice)


async def keep_caller_heard(session: AsyncSession, call: str, hearing: Mapping[str, Any]) -> None:
    """Keep how a simulated spoken call was heard, against what its caller really said, with the call's facts."""
    await FactsRepository(session).keep(call, hearing=dict(hearing))


# The caller is kept with them: a comparison's table names each row's caller from the first read,
# before the seal folds the call.
async def keep_agent_values(
    session: AsyncSession,
    call: str,
    *,
    against: Mapping[str, Any] | None,
    comparison: str | None,
    persona: str | None = None,
) -> None:
    """Keep the voice and models the agent runs on for the call over its settings, its comparison and caller."""
    await FactsRepository(session).keep(
        call, against=None if against is None else dict(against), comparison=comparison, persona=persona
    )
