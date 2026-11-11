"""What an org used in a month: the totals the database's triggers count from the log."""

from dataclasses import dataclass
from datetime import date

from sqlalchemy.ext.asyncio import AsyncSession

from runtime.billing.repository import UsageTotalRepository
from runtime.enums import Env
from runtime.postgres import without_timeouts


@dataclass(frozen=True, slots=True)
class Usage:
    """What was consumed in a month: calls, minutes, turns, tokens, characters, evals, the cost."""

    calls: int = 0
    minutes: float = 0.0
    messages: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    characters: int = 0
    evals: int = 0
    simulations: int = 0
    cost_usd: float = 0.0

    @property
    def llm_tokens(self) -> int:
        """The tokens the models read and wrote."""
        return self.input_tokens + self.output_tokens


async def get_usage(session: AsyncSession, org: str, env: Env, month: date) -> Usage:
    """What the org's calls in the env consumed in the month; nothing when it made none."""
    row = await UsageTotalRepository(session).find(org, env, month.replace(day=1))
    if row is None:
        return Usage()
    return Usage(
        calls=row.calls,
        minutes=row.minutes,
        messages=row.messages,
        input_tokens=row.input_tokens,
        output_tokens=row.output_tokens,
        characters=row.characters,
        evals=row.evals,
        simulations=row.simulations,
        cost_usd=row.cost_usd,
    )


async def sum_spent(session: AsyncSession, org: str, month: date) -> float:
    """What the org's calls in both envs cost in the month."""
    return await UsageTotalRepository(session).sum_cost(org, month.replace(day=1))


# Long on purpose: every metered entry of the log is read once.
async def rebuild_usage_totals(session: AsyncSession) -> int:
    """Count every org's totals again from the log, as the database's triggers count them; the rows."""
    async with without_timeouts(session):
        return await UsageTotalRepository(session).rebuild()
