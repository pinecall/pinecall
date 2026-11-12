"""What an erasure deletes of an org's logs: their entries, the private values aside, their facts, their heads."""

from sqlalchemy import delete, select, text

from runtime.calls.models import CallFact, CallLog, CallLogHead, CallPrivate
from runtime.kit.repository import Repository

# The trigger on call_log lets a DELETE through in the transaction that set this, and no other
# (migrations/sql/0011_erasure.sql).
LET_DELETES_THROUGH = text("SET LOCAL pinecall.erasing = 'on'")


class ErasureRepository(Repository[CallLogHead]):
    """The deletes an org's erasure makes of its logs, in the order the log's trigger needs."""

    model = CallLogHead

    # The entries go before the heads: call_log's trigger reads each summary's org off its head, to
    # take its usage out of the org's totals (migrations/sql/0023_usage_totals.sql). The openings and
    # the configs go with the org, by their key to it.
    async def delete_logs_of_org(self, org: str) -> int:
        """Delete every log of the org, its calls' and its agents' own; how many logs went."""
        logs = select(CallLogHead.log).where(CallLogHead.org == org)
        await self.session.execute(LET_DELETES_THROUGH)
        await self.change(delete(CallLog).where(CallLog.log.in_(logs)))
        await self.change(delete(CallPrivate).where(CallPrivate.log.in_(logs)))
        await self.change(delete(CallFact).where(CallFact.call.in_(logs)))
        return await self.change(delete(CallLogHead).where(CallLogHead.org == org))
