"""The spend an org's calls add up to, by the day each started, for the alert that watches it."""

from sqlalchemy import func, select

from runtime.calls.models import CallFact, CallLogHead
from runtime.kit.repository import Repository


class SpendRepository(Repository[CallFact]):
    """What the org's calls cost by the day each started, both envs and every holder."""

    model = CallFact

    # Read off the facts, which the summary folded its cost into, by the day the call started;
    # the dollars are the org's whoever held the call.
    async def sum_today_and_before(self, org: str, day: float, since: float) -> tuple[float, float]:
        """The org's spend from the day's start, and from `since` to it."""
        statement = (
            select(
                func.coalesce(func.sum(CallFact.cost_usd).filter(CallLogHead.started_at >= day), 0.0).label("today"),
                func.coalesce(func.sum(CallFact.cost_usd).filter(CallLogHead.started_at < day), 0.0).label("before"),
            )
            .select_from(CallLogHead)
            .join(CallFact, CallFact.call == CallLogHead.log)
            .where(CallLogHead.org == org, CallLogHead.call.is_not(None), CallLogHead.started_at >= since)
        )
        row = (await self.session.execute(statement)).one()
        return float(row.today), float(row.before)
