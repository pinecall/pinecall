"""Every statement on the billing tables: quotas and the monthly usage totals."""

from datetime import date

from sqlalchemy import delete, func, literal, select, text

from runtime.billing.models import Quota, UsageTotal
from runtime.enums import Env
from runtime.kit.repository import Repository
from runtime.kit.time import now


class QuotaRepository(Repository[Quota]):
    """An org's limits, one row per env."""

    model = Quota

    async def find(self, org: str, env: Env) -> Quota | None:
        """The org's row in the env, or None."""
        return await self.one_or_none(self.statement().where(Quota.org == org, Quota.env == env))

    async def put(self, org: str, env: Env, **limits: object) -> Quota:
        """Replace the row whole: a limit left out stops being one."""
        return await self.upsert({"org": org, "env": env, "set_at": now(), **limits}, key=["org", "env"])

    # A stock (agents, numbers, hosted apps, facts) is counted by its owner and then added to: the
    # lock is taken before the count, for the transaction, so two requests at the limit count in turn.
    async def lock(self, org: str, env: Env, quota: str) -> None:
        """Hold the org's quota in the env for this transaction."""
        held = func.pg_advisory_xact_lock(func.hashtext(literal(f"quota {org} {env} {quota}")))
        await self.session.execute(select(held))


HELD = text("lock table usage_totals in exclusive mode")
RECOUNTED = text("""
select usage_counted(coalesce(jsonb_agg(jsonb_build_object(
    'org', head.org, 'env', usage_world(entry.type, entry.data, head.env), 'ts', entry.ts,
    'type', entry.type, 'data', entry.data, 'opened_by', head.opened_by)), '[]'), 1)
from call_log entry join call_log_head head on head.log = entry.log
where entry.type in ('call.summary', 'call.score', 'evals.spent') and head.org is not null
""")


class UsageTotalRepository(Repository[UsageTotal]):
    """What an org used, one row per env and UTC month; written by the database's triggers."""

    model = UsageTotal

    async def find(self, org: str, env: Env, month: date) -> UsageTotal | None:
        """The month's row, or None."""
        return await self.one_or_none(
            self.statement().where(UsageTotal.org == org, UsageTotal.env == env, UsageTotal.period == month)
        )

    async def sum_cost(self, org: str, month: date) -> float:
        """What the org's calls in both envs cost in the month."""
        statement = select(func.coalesce(func.sum(UsageTotal.cost_usd), 0.0)).where(
            UsageTotal.org == org, UsageTotal.period == month
        )
        return float((await self.session.execute(statement)).scalar_one())

    # One transaction, the table locked: the fold is the triggers' own (migrations/sql/0106), so a
    # rebuild counts exactly what a write would have (migrations/versions/20261023_000013 is the newest).
    async def rebuild(self) -> int:
        """Forget every row and count them again from every metered entry; how many rows."""
        await self.session.execute(HELD)
        await self.session.execute(delete(UsageTotal))
        await self.session.execute(RECOUNTED)
        return int((await self.session.execute(select(func.count()).select_from(UsageTotal))).scalar_one())
