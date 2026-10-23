"""Quotas and admission: an org's limits in an env against what it used there, before it uses more."""

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from typing import Any, cast

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from pinecall_runtime.billing.repository import QuotaRepository, UsageTotalRepository
from pinecall_runtime.enums import Env
from pinecall_runtime.exceptions import QuotaExceeded, ValidationError
from pinecall_runtime.kit.time import month_of
from pinecall_runtime.platform import service as platform
from pinecall_runtime.postgres import unbounded
from pinecall_runtime.wire.parts import QuotaName

ADMISSION = "admission"
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

    def __post_init__(self) -> None:
        for name, limit in self.limits.items():
            if limit is not None and limit < 0:
                raise ValidationError(f"a quota is a count, and {name} cannot be {limit}")

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


@dataclass(frozen=True, slots=True)
class Ceiling:
    """How long a call admitted may last: what is left of the org's minutes."""

    seconds: int
    minutes: int


class Admission(BaseModel):
    """What a newborn org may use in each env: a person's first org, and any later one."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    first: dict[Env, Quotas] = Field(default_factory=dict[Env, Quotas])
    # None gives a later org what the first got; set, one trial per person.
    later: dict[Env, Quotas] | None = None


class LimitReached(QuotaExceeded):
    """The org has used all of one of its quotas in the env."""

    def __init__(self, env: Env, quota: QuotaName, used: float, limit: int) -> None:
        shown = int(used) if float(used).is_integer() else round(used, 2)
        super().__init__(
            f"the org has used {shown} of its {limit} {quota.replace('_', ' ')} in the {env}",
            quota=quota,
            used=used,
            limit=limit,
        )


class BudgetReached(QuotaExceeded):
    """The org has spent its month's budget, both envs together."""

    def __init__(self, used: float, limit: int) -> None:
        super().__init__(
            f"the org has spent {round(used, 2)} of its {limit} USD budget this month",
            quota="budget_usd",
            used=used,
            limit=limit,
        )


# ── quotas ──


async def get_quotas(session: AsyncSession, org: str, env: Env) -> Quotas:
    """The org's limits in the env; none when nobody set them."""
    row = await QuotaRepository(session).get(org, env)
    if row is None:
        return Quotas()
    return Quotas(
        **{name: getattr(row, name) for name in QUOTA_NAMES},
        lends=None if row.lends is None else frozenset(row.lends),
    )


async def set_quotas(session: AsyncSession, org: str, env: Env, quotas: Quotas) -> None:
    """Replace the org's limits in the env, whole."""
    lends = None if quotas.lends is None else sorted(quotas.lends)
    limits = cast(Mapping[str, Any], quotas.limits)
    await QuotaRepository(session).put(org, env, **limits, lends=lends)


async def get_admission(session: AsyncSession) -> Admission:
    """What a newborn org is given; nothing limited on a box that never said."""
    value = await platform.get_setting(session, ADMISSION)
    return Admission() if value is None else Admission.model_validate(value)


async def set_admission(session: AsyncSession, allowed: Admission) -> None:
    """Write what a newborn org is given, whole."""
    await platform.put_setting(session, ADMISSION, allowed.model_dump(mode="json"))


async def give_first_quotas(session: AsyncSession, org: str, *, already: int) -> None:
    """Set a newborn org's quotas in each env, as the box's admission says for its person."""
    allowed = await get_admission(session)
    envs = allowed.first if allowed.later is None or already == 0 else allowed.later
    for env, quotas in envs.items():
        await set_quotas(session, org, env, quotas)


# ── usage ──


async def get_usage(session: AsyncSession, org: str, env: Env, month: date) -> Usage:
    """What the org's calls in the env consumed in the month."""
    row = await UsageTotalRepository(session).get(org, env, month.replace(day=1))
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


# Long on purpose: every metered entry of the log is read once.
async def rebuild_usage_totals(session: AsyncSession) -> int:
    """Count every org's totals again from the log, as the database's triggers count them; the rows."""
    async with unbounded(session):
        return await UsageTotalRepository(session).rebuild()


async def spent_in_month(session: AsyncSession, org: str, month: date) -> float:
    """What the org's calls in both envs cost in the month."""
    return await UsageTotalRepository(session).spent_in(org, month.replace(day=1))


# ── admission: one more of something ──


# `at` is the log's clock, so a call is held to the month its summary will be counted in.
async def admit_call(session: AsyncSession, org: str, env: Env, *, running: int, at: float) -> Ceiling | None:
    """Admit one more call, with its ceiling; None when the org's minutes have no limit."""
    quotas = await get_quotas(session, org, env)
    _refuse_past(quotas, env, "concurrent_calls", running)
    month = month_of(at)
    if quotas.budget_usd is not None:
        spent = await spent_in_month(session, org, month)
        limit = quotas.limit_reached("budget_usd", spent)
        if limit is not None:
            raise BudgetReached(spent, limit)
    if quotas.minutes is None and quotas.messages is None and quotas.llm_tokens is None:
        return None
    used = await get_usage(session, org, env, month)
    _refuse_past(quotas, env, "minutes", used.minutes)
    _refuse_past(quotas, env, "messages", used.messages)
    _refuse_past(quotas, env, "llm_tokens", used.input_tokens + used.output_tokens)
    if quotas.minutes is None:
        return None
    # Never zero: the worker reads a zero ceiling as none.
    return Ceiling(seconds=max(1, int((quotas.minutes - used.minutes) * 60)), minutes=quotas.minutes)


async def admit_turn(session: AsyncSession, org: str, env: Env, *, turns: int, tokens: int, at: float) -> None:
    """Admit one more turn of a written call already this long."""
    quotas = await get_quotas(session, org, env)
    if quotas.messages is None and quotas.llm_tokens is None:
        return
    used = await get_usage(session, org, env, month_of(at))
    _refuse_past(quotas, env, "messages", used.messages + turns)
    _refuse_past(quotas, env, "llm_tokens", used.input_tokens + used.output_tokens + tokens)


async def admit_agent(session: AsyncSession, org: str, env: Env, *, holding: int) -> None:
    """Admit one more agent held by the org's apps."""
    _refuse_past(await get_quotas(session, org, env), env, "agents", holding)


async def admit_number(session: AsyncSession, org: str, env: Env, *, bought: int) -> None:
    """Admit one more number bought on the box's carrier account for the org."""
    _refuse_past(await get_quotas(session, org, env), env, "numbers", bought)


async def admit_memory(session: AsyncSession, org: str, env: Env, *, kept: int) -> None:
    """Admit one more fact remembered about a contact."""
    _refuse_past(await get_quotas(session, org, env), env, "memory_facts", kept)


async def admit_seat(session: AsyncSession, org: str, env: Env, *, seated: int) -> None:
    """Admit one more person seated in the org, which holds `seated` already."""
    _refuse_past(await get_quotas(session, org, env), env, "seats", seated)


async def admit_hosted_app(session: AsyncSession, org: str, env: Env, *, hosting: int) -> None:
    """Admit one more app the box hosts for the org."""
    _refuse_past(await get_quotas(session, org, env), env, "hosted_apps", hosting)


# A simulation counts once its call ends, and a call begun is a simulation admitted: `playing` is those
# that have begun and not ended yet, so a burst of them cannot all pass the limit together.
async def admit_simulation(session: AsyncSession, org: str, env: Env, *, at: float, playing: int = 0) -> None:
    """Admit one more call a simulated caller plays."""
    quotas = await get_quotas(session, org, env)
    if quotas.simulations is None:
        return
    used = await get_usage(session, org, env, month_of(at))
    _refuse_past(quotas, env, "simulations", used.simulations + playing)


async def admit_evals(session: AsyncSession, org: str, env: Env, *, at: float) -> int | None:
    """The evals the org may still spend this month; None when unlimited; refused once none are left."""
    quotas = await get_quotas(session, org, env)
    if quotas.evals is None:
        return None
    used = await get_usage(session, org, env, month_of(at))
    _refuse_past(quotas, env, "evals", used.evals)
    return quotas.evals - used.evals


async def admit_push(session: AsyncSession, org: str, env: Env, *, keeping: int) -> None:
    """Admit a knowledge push that leaves the org keeping this many chunks; refused whole."""
    quotas = await get_quotas(session, org, env)
    limit = quotas.limit_exceeded("knowledge_chunks", keeping)
    if limit is not None:
        raise LimitReached(env, "knowledge_chunks", keeping, limit)


def _refuse_past(quotas: Quotas, env: Env, quota: QuotaName, used: float) -> None:
    limit = quotas.limit_reached(quota, used)
    if limit is not None:
        raise LimitReached(env, quota, used, limit)
