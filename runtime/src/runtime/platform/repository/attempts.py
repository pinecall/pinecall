"""The knocks table: attempts by name, in a sliding window, across every gateway."""

from sqlalchemy import delete, func, literal, select

from runtime.kit.repository import Repository
from runtime.platform.models import Attempt


class AttemptRepository(Repository[Attempt]):
    """Attempts by name."""

    model = Attempt

    # The lock is the name's, for the transaction: two gateways counting the same name at once count in turn.
    async def count_and_record(self, name: str, at: float, window_s: float) -> int:
        """Record one attempt and answer how many the name made in the window, this one included."""
        await self.session.execute(delete(Attempt).where(Attempt.at < at - window_s))
        await self.session.execute(select(func.pg_advisory_xact_lock(func.hashtext(literal(name)))))
        await self.add(Attempt(name=name, at=at), flush=True)
        return await self.count(self.statement().where(Attempt.name == name, Attempt.at >= at - window_s))
