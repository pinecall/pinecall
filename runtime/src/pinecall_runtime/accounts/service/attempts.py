"""Sign-in attempts throttled per name across every gateway: so many a minute, then wait."""

from collections.abc import Callable

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from pinecall_runtime.accounts.repository import SignInAttemptRepository
from pinecall_runtime.exceptions import TooManyRequests
from pinecall_runtime.kit.time import epoch

WINDOW_S = 60.0
# Every attempt counts, not only the misses: counting misses would say which guess was right.
SIGN_IN_TRIES = 5
# A password is also so many a minute from one place whatever the address, and at one address from
# wherever: a list of addresses tried from one machine, or one address tried from a list of
# machines, meets the same minute's wait as a person who mistyped five times.
PASSWORD_TRIES_A_PLACE = 20
PASSWORD_TRIES_AN_ADDRESS = 20


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


class PasswordThrottle:
    """A password tried: five a minute per address from one place, and a budget per place and per address."""

    def __init__(self, sessions: async_sessionmaker[AsyncSession], clock: Callable[[], float] = epoch) -> None:
        self.each = AttemptThrottle(sessions, SIGN_IN_TRIES, clock)
        self.a_place = AttemptThrottle(sessions, PASSWORD_TRIES_A_PLACE, clock)
        self.an_address = AttemptThrottle(sessions, PASSWORD_TRIES_AN_ADDRESS, clock)

    async def check(self, client: str, email: str, org: str | None = None) -> None:
        """TooManyAttempts once any of the three counts is past its tries; the sentence is the same whichever."""
        await self.each.check(f"{client} {org or '*'}/{email}", email)
        await self.a_place.check(f"place {client}", email)
        await self.an_address.check(f"address {email}", email)
