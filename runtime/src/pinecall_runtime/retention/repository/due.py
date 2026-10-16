"""What the calendar takes: sealed calls past their org's days, and records and dials past two years."""

from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import delete, func, select

from pinecall_runtime.calls.models import CallLogHead
from pinecall_runtime.compliance.models import OrgPolicy
from pinecall_runtime.enums import Env
from pinecall_runtime.kit.repository import Repository
from pinecall_runtime.retention.models import CallRecord
from pinecall_runtime.telephony.models import Dial

A_DAY_S = 86_400


@dataclass(frozen=True, slots=True)
class DueCall:
    """A sealed call past its org's days, and whose it is."""

    call: str
    org: str
    env: Env
    holder: str | None


class DueRepository(Repository[CallLogHead]):
    """Every statement of the nightly run reads and deletes across every org's years."""

    model = CallLogHead

    # Sealed calls only: a call still running is the caller's, not the calendar's. Oldest first, so
    # a run cut short by its limit takes up where it stopped.
    async def due(self, now: float, *, limit: int) -> list[DueCall]:
        """The sealed calls whose org keeps fewer days than they have, oldest first."""
        statement = (
            select(CallLogHead.call, CallLogHead.org, CallLogHead.env, CallLogHead.holder)
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
        rows = (await self.session.execute(statement)).all()
        return [DueCall(str(call), str(org), Env(str(env)), holder) for call, org, env, holder in rows]

    # A record of a call that never started goes by when it ended, or when it was erased.
    async def forget_records(self, before: float) -> int:
        """Delete the records of erased calls older than the moment; how many."""
        went = func.coalesce(CallRecord.started_at, CallRecord.ended_at, func.extract("epoch", CallRecord.erased_at))
        return await self.changed(delete(CallRecord).where(went < before))

    async def forget_dials(self, before: float) -> int:
        """Delete the dials placed or refused before the moment; how many."""
        return await self.changed(delete(Dial).where(Dial.at < datetime.fromtimestamp(before, UTC)))
