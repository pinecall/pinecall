"""What an erasure takes of the calls: the logs a subject owns, found, and each one's rows deleted in order."""

from collections.abc import Sequence

from sqlalchemy import delete, select, text

from runtime.calls.models import CallFact, CallLog, CallLogHead, CallOpening, CallPrivate
from runtime.enums import Env
from runtime.kit.repository import Repository

# The trigger on call_log lets a DELETE through in the transaction that set this, and no other
# (migrations/sql/0011_erasure.sql).
LET_DELETES_THROUGH = text("SET LOCAL pinecall.erasing = 'on'")


class ErasureRepository(Repository[CallLogHead]):
    """The logs an org, an agent or a contact owns, and the deletes that take a log, in the order its trigger needs."""

    model = CallLogHead

    # ── what there is to erase ──

    async def list_of_org(self, org: str) -> Sequence[CallLogHead]:
        """Every log of the org: its calls, and its agents' own logs, which carry no call."""
        return await self.all(self.statement().where(CallLogHead.org == org))

    async def list_of_agent(self, org: str, agent: str) -> Sequence[CallLogHead]:
        """Every log of one agent of the org, both envs and every holder: its calls and its own log."""
        return await self.all(self.statement().where(CallLogHead.org == org, CallLogHead.agent == agent))

    async def list_of_contact(self, org: str, env: Env, contact: str) -> Sequence[CallLogHead]:
        """Every call of the contact in the env, by its head."""
        statement = (
            self.statement()
            .join(CallFact, CallFact.call == CallLogHead.call)
            .where(CallLogHead.org == org, CallLogHead.env == env, CallFact.contact == contact)
        )
        return await self.all(statement)

    # ── a log's rows ──

    # The entries go before the heads: call_log's trigger reads each summary's org off its head, to
    # take its usage out of the org's totals (migrations/sql/0023_usage_totals.sql).
    async def delete_logs(self, logs: Sequence[str], calls: Sequence[str]) -> int:
        """Delete the logs' entries, what they sealed aside, their heads, facts and openings; how many entries."""
        await self.session.execute(LET_DELETES_THROUGH)
        entries = await self.change(delete(CallLog).where(CallLog.log.in_(logs)))
        await self.change(delete(CallPrivate).where(CallPrivate.log.in_(logs)))
        await self.change(delete(CallLogHead).where(CallLogHead.log.in_(logs)))
        await self.change(delete(CallFact).where(CallFact.call.in_(calls)))
        await self.change(delete(CallOpening).where(CallOpening.call.in_(calls)))
        return entries

    async def list_named(self, calls: Sequence[str]) -> Sequence[CallLogHead]:
        """The heads of the calls named, those that still have one."""
        return await self.all(select(CallLogHead).where(CallLogHead.call.in_(calls)))
