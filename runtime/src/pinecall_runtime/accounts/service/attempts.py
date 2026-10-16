"""Sign-in attempts throttled per name across every gateway: so many a minute, then wait."""

from collections.abc import Callable

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from pinecall_runtime.accounts.repository import SignInAttemptRepository
from pinecall_runtime.exceptions import TooManyRequests
from pinecall_runtime.kit.time import epoch

WINDOW_S = 60.0
# Every attempt counts, not only the misses: counting misses would say which guess was right.
SIGN_IN_TRIES = 5


class TooManyAttempts(TooManyRequests):
    """The name tried too often in the last minute."""

    def __init__(self, what: str) -> None:
        super().__init__(f"too many attempts for {what}: try again in a minute", retry_after_s=60)


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
        async with self.sessions() as session:
            counted = await SignInAttemptRepository(session).count_and_record(name, self.clock(), WINDOW_S)
            await session.commit()
        return counted <= self.tries

    async def check(self, name: str, what: str) -> None:
        """TooManyAttempts past the window's tries."""
        if not await self.is_allowed(name):
            raise TooManyAttempts(what)
