"""Attempts throttled per name across every gateway: so many a minute, then wait."""

from collections.abc import Callable

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from runtime.exceptions import TooManyRequests
from runtime.kit.time import A_MINUTE_S, epoch
from runtime.platform.repository.attempts import AttemptRepository

WINDOW_S = float(A_MINUTE_S)


class TooManyAttempts(TooManyRequests):
    """The name tried too often in the last minute."""

    def __init__(self, what: str) -> None:
        super().__init__(f"too many attempts for {what}: try again in a minute", retry_after_s=A_MINUTE_S)


# Every attempt counts, not only the misses: counting misses would say which guess was right. Counted
# in a transaction of its own, so the count stands whatever the request it guards does next.
class AttemptThrottle:
    """So many attempts a minute per name, counted in Postgres."""

    def __init__(
        self, sessions: async_sessionmaker[AsyncSession], tries: int, clock: Callable[[], float] = epoch
    ) -> None:
        self.sessions = sessions
        self.tries = tries
        self.clock = clock

    async def is_allowed(self, name: str) -> bool:
        """Count an attempt and say whether it is within the window's tries."""
        async with self.sessions.begin() as session:
            counted = await AttemptRepository(session).count_and_record(name, self.clock(), WINDOW_S)
        return counted <= self.tries

    async def check(self, name: str, what: str) -> None:
        """TooManyAttempts past the window's tries."""
        if not await self.is_allowed(name):
            raise TooManyAttempts(what)
