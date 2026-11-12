"""What the calendar takes: the sealed calls past their org's days."""

from dataclasses import dataclass

from sqlalchemy import select

from runtime.calls.models import CallLogHead
from runtime.compliance.models import OrgPolicy
from runtime.enums import Env
from runtime.kit.repository import Repository
from runtime.kit.time import A_DAY_S


@dataclass(frozen=True, slots=True)
class Due:
    """A sealed call past its org's days: which, and whose."""

    call: str
    org: str
    env: Env


class DueRepository(Repository[CallLogHead]):
    """The sealed calls each org's policy no longer keeps, across every org."""

    model = CallLogHead

    # Sealed calls only: a call still running is the caller's, not the calendar's. Oldest first, so
    # a run cut short by its limit takes up where it stopped.
    async def list_due(self, now: float, *, limit: int) -> list[Due]:
        """The sealed calls whose org keeps fewer days than they have, oldest first."""
        statement = (
            select(CallLogHead.call, CallLogHead.org, CallLogHead.env)
            .join(OrgPolicy, OrgPolicy.org == CallLogHead.org)
            .where(
                CallLogHead.call.is_not(None),
                CallLogHead.sealed,
                CallLogHead.started_at.is_not(None),
                CallLogHead.env.is_not(None),
                OrgPolicy.retention_days.is_not(None),
                CallLogHead.started_at < now - OrgPolicy.retention_days * A_DAY_S,
            )
            .order_by(CallLogHead.started_at)
            .limit(limit)
        )
        rows = await self.session.execute(statement)
        return [Due(str(call), str(org), Env(str(env))) for call, org, env in rows]
