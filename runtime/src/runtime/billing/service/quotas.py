"""An org's quotas in one env: the limits by name, the lends, how its simulations are shaped."""

import dataclasses
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Self, cast

from sqlalchemy.ext.asyncio import AsyncSession

from runtime.billing.repository import QuotaRepository
from runtime.enums import Env
from runtime.exceptions import ValidationError
from runtime.wire.parts import QuotaName

# What an org nobody gave more is held to. A simulation takes a seat of the fleet beside the real
# callers and a share of the gateway that plays its caller: ten are ~2.5 vCPU of a worker's machine.
SIMULATIONS_AT_ONCE = 10
# The calls one comparison places, every caller against every setup as many times as asked.
COMPARISON_CALLS = 10
# The one list of the quotas' names: `Quotas` has a field for each, and a test holds the two together.
QUOTA_NAMES: tuple[QuotaName, ...] = (
    "minutes",
    "messages",
    "agents",
    "concurrent_calls",
    "memory_facts",
    "knowledge_chunks",
    "numbers",
    "seats",
    "llm_tokens",
    "hosted_apps",
    "evals",
    "simulations",
    "budget_usd",
)
# Seats and the budget are the org's, not an env's: they are read from this env's row, always.
THE_ORGS_ROW = Env.production


# None is no limit (the self-hosted default). Zero is a real limit that refuses everything.
@dataclass(frozen=True, slots=True)
class Quotas:
    """An org's limits in one env, its monthly budget, and the box keys lent to it."""

    minutes: int | None = None
    messages: int | None = None
    agents: int | None = None
    concurrent_calls: int | None = None
    memory_facts: int | None = None
    knowledge_chunks: int | None = None
    numbers: int | None = None
    seats: int | None = None
    llm_tokens: int | None = None
    hosted_apps: int | None = None
    evals: int | None = None
    simulations: int | None = None
    budget_usd: int | None = None
    # Box vendor keys the org may use: None all, empty none, else `vendor` or `vendor/model`.
    lends: frozenset[str] | None = None
    # How the org's simulations are shaped: None is the platform's own, never no limit, since each
    # one on the line is a seat of the fleet somebody else's call would take.
    simulations_at_once: int | None = None
    comparison_calls: int | None = None

    def __post_init__(self) -> None:
        named: list[tuple[str, int | None]] = list(self.limits.items())
        named += [("simulations_at_once", self.simulations_at_once), ("comparison_calls", self.comparison_calls)]
        for name, limit in named:
            if limit is not None and limit < 0:
                raise ValidationError(f"a quota is a count, and {name} cannot be {limit}")

    @classmethod
    def of_limits(
        cls,
        limits: Mapping[QuotaName, int | None],
        *,
        lends: frozenset[str] | None = None,
        simulations_at_once: int | None = None,
        comparison_calls: int | None = None,
    ) -> Self:
        """The quotas from limits by name; a name left out is no limit."""
        named = cast(dict[str, Any], {name: limits.get(name) for name in QUOTA_NAMES})
        return cls(**named, lends=lends, simulations_at_once=simulations_at_once, comparison_calls=comparison_calls)

    @property
    def simulating_at_most(self) -> int:
        """The simulated calls the org may have on the line at once in the env."""
        return SIMULATIONS_AT_ONCE if self.simulations_at_once is None else self.simulations_at_once

    @property
    def compared_at_most(self) -> int:
        """The calls one comparison of the org may place."""
        return COMPARISON_CALLS if self.comparison_calls is None else self.comparison_calls

    @property
    def limits(self) -> Mapping[QuotaName, int | None]:
        """Every limit by its name."""
        return {name: getattr(self, name) for name in QUOTA_NAMES}

    def limit_reached(self, quota: QuotaName, used: float) -> int | None:
        """The limit when `used` is at or past it, else None."""
        limit = self.limits[quota]
        return limit if limit is not None and used >= limit else None

    def limit_exceeded(self, quota: QuotaName, keeping: float) -> int | None:
        """The limit when `keeping` would pass it, else None; for pushes sized up front."""
        limit = self.limits[quota]
        return limit if limit is not None and keeping > limit else None

    def is_switched_off(self, quota: QuotaName) -> bool:
        """Whether the quota is zero: the feature is not in the plan."""
        return self.limits[quota] == 0


async def get_quotas(session: AsyncSession, org: str, env: Env) -> Quotas:
    """The org's limits in the env; none when nobody set them."""
    row = await QuotaRepository(session).find(org, env)
    if row is None:
        return Quotas()
    return Quotas.of_limits(
        {name: getattr(row, name) for name in QUOTA_NAMES},
        lends=None if row.lends is None else frozenset(row.lends),
        simulations_at_once=row.simulations_at_once,
        comparison_calls=row.comparison_calls,
    )


async def put_quotas(session: AsyncSession, org: str, env: Env, quotas: Quotas) -> None:
    """Replace the org's quotas in the env, whole."""
    lends = None if quotas.lends is None else sorted(quotas.lends)
    limits = cast(Mapping[str, Any], quotas.limits)
    shaped = {"simulations_at_once": quotas.simulations_at_once, "comparison_calls": quotas.comparison_calls}
    await QuotaRepository(session).put(org, env, **limits, lends=lends, **shaped)


# A plan's book writes the month's limits and lends: how the org's simulations are shaped stands.
async def put_limits(
    session: AsyncSession, org: str, env: Env, limits: Mapping[QuotaName, int | None], lends: frozenset[str] | None
) -> Quotas:
    """Replace the org's limits and lends in the env; its simulations' shape is kept."""
    standing = await get_quotas(session, org, env)
    quotas = Quotas.of_limits(
        limits,
        lends=lends,
        simulations_at_once=standing.simulations_at_once,
        comparison_calls=standing.comparison_calls,
    )
    await put_quotas(session, org, env, quotas)
    return quotas


# Not a month's count but a shape: a ceiling on the fleet's seats the org's simulated callers take at
# once, and on what one comparison places. The org's limits and lends are kept.
async def put_simulating(
    session: AsyncSession, org: str, env: Env, *, simulations_at_once: int | None, comparison_calls: int | None
) -> Quotas:
    """Replace how the org's simulations are shaped in the env; None is the platform's own."""
    standing = await get_quotas(session, org, env)
    quotas = dataclasses.replace(standing, simulations_at_once=simulations_at_once, comparison_calls=comparison_calls)
    await put_quotas(session, org, env, quotas)
    return quotas


async def hold_stock(session: AsyncSession, org: str, env: Env, quota: QuotaName) -> None:
    """Hold one of the org's stocks for this transaction: called before counting it, to admit one more."""
    await QuotaRepository(session).lock(org, env, quota)
