"""One more of something, admitted or refused: an org's quotas held against what it uses, before it uses more."""

from collections.abc import Sequence
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from runtime.billing.service.quotas import THE_ORGS_ROW, Quotas, get_quotas
from runtime.billing.service.usage import get_usage, sum_spent
from runtime.enums import Env
from runtime.exceptions import QuotaExceeded
from runtime.kit.time import month_of
from runtime.wire.parts import QuotaName


@dataclass(frozen=True, slots=True)
class Ceiling:
    """How long a call admitted may last: what is left of the org's minutes."""

    seconds: int
    minutes: int


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


# Named so the person knows what to end: an org of one seat whose own test call still runs read
# `1 of its 1 concurrent calls` and did not know the call was its own (2026-11-04).
NAMED_AT_MOST = 3


class SeatsTaken(LimitReached):
    """Every call the org may run at once in the env is running: the calls that hold the seats, named."""

    def __init__(self, env: Env, running: Sequence[str], limit: int) -> None:
        super().__init__(env, "concurrent_calls", len(running), limit)
        self.calls = tuple(running)
        named = ", ".join(running[:NAMED_AT_MOST])
        more = f" and {len(running) - NAMED_AT_MOST} more" if len(running) > NAMED_AT_MOST else ""
        each = "it" if len(running) == 1 else "them"
        self.message = (
            f"{self.message}: {named}{more} still open — end {each} in the console's Calls, or wait for "
            f"{each} to end; a test and a simulation each count as a call"
        )
        self.args = (self.message,)


class BudgetReached(QuotaExceeded):
    """The org has spent its month's budget, both envs together."""

    def __init__(self, used: float, limit: int) -> None:
        super().__init__(
            f"the org has spent {round(used, 2)} of its {limit} USD budget this month",
            quota="budget_usd",
            used=used,
            limit=limit,
        )


# `at` is the log's clock, so a call is held to the month its summary will be counted in; `running`
# is the org's calls open in the env now, so a refusal can say which ones hold the seats. The budget
# is the org's, both envs together, so it is read from the org's own row whatever env the call is in:
# read from the calling env's row, a budget set on production never stopped the sandbox.
async def admit_call(session: AsyncSession, org: str, env: Env, *, running: Sequence[str], at: float) -> Ceiling | None:
    """Admit one more call, with its ceiling; None when the org's minutes have no limit."""
    quotas = await get_quotas(session, org, env)
    seats = quotas.limit_reached("concurrent_calls", len(running))
    if seats is not None:
        raise SeatsTaken(env, running, seats)
    month = month_of(at)
    budget = quotas if env is THE_ORGS_ROW else await get_quotas(session, org, THE_ORGS_ROW)
    if budget.budget_usd is not None:
        spent = await sum_spent(session, org, month)
        limit = budget.limit_reached("budget_usd", spent)
        if limit is not None:
            raise BudgetReached(spent, limit)
    if quotas.minutes is None and quotas.messages is None and quotas.llm_tokens is None:
        return None
    used = await get_usage(session, org, env, month)
    _refuse_past(quotas, env, "minutes", used.minutes)
    _refuse_past(quotas, env, "messages", used.messages)
    _refuse_past(quotas, env, "llm_tokens", used.llm_tokens)
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
    _refuse_past(quotas, env, "llm_tokens", used.llm_tokens + tokens)


# The four stocks: counted by the domain that owns them, after it took `quotas.hold_stock` in the same
# transaction, so two requests at the limit are admitted in turn and the second is refused.
async def admit_agent(session: AsyncSession, org: str, env: Env, *, holding: int) -> None:
    """Admit one more agent held by the org's apps."""
    _refuse_past(await get_quotas(session, org, env), env, "agents", holding)


async def admit_number(session: AsyncSession, org: str, env: Env, *, bought: int) -> None:
    """Admit one more number bought on the box's carrier account for the org."""
    _refuse_past(await get_quotas(session, org, env), env, "numbers", bought)


async def admit_memory(session: AsyncSession, org: str, env: Env, *, kept: int) -> None:
    """Admit one more fact remembered about a contact."""
    _refuse_past(await get_quotas(session, org, env), env, "memory_facts", kept)


async def admit_hosted_app(session: AsyncSession, org: str, env: Env, *, hosting: int) -> None:
    """Admit one more app the box hosts for the org."""
    _refuse_past(await get_quotas(session, org, env), env, "hosted_apps", hosting)


# A seat is the org's, not an env's: held to the org's own row, as the page that shows it reads it.
async def admit_seat(session: AsyncSession, org: str, *, seated: int) -> None:
    """Admit one more person seated in the org, which holds `seated` already."""
    _refuse_past(await get_quotas(session, org, THE_ORGS_ROW), THE_ORGS_ROW, "seats", seated)


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
