"""The keys a gateway verified lately: remembered for seconds, and forgotten on every gateway at a revocation."""

import time
from collections.abc import Callable
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from runtime.accounts.service.actor import Verified, verify_key
from runtime.kit import crypto
from runtime.kit.commit import run_after_commit
from runtime.kit.time import now
from runtime.signal import Signal
from runtime.wire.signal import Forgotten

# Verifying a key is a round trip per request. A key is remembered this long on each gateway; a
# revocation or a change to its person is said on the signal (`wire.signal.Forgotten`) and forgets it
# everywhere at once.
REMEMBERED_FOR_S = 5.0
FORGET_CHANNEL = "keys:forgotten"


@dataclass(frozen=True, slots=True)
class Remembered:
    """A key verified, and until when this gateway trusts that without asking the database."""

    verified: Verified
    until: float


class KeyCache:
    """The keys this gateway verified lately, and the revocations it hears from the others."""

    def __init__(
        self,
        sessions: async_sessionmaker[AsyncSession],
        signal: Signal,
        *,
        for_s: float = REMEMBERED_FOR_S,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.sessions = sessions
        self.signal = signal
        self.for_s = for_s
        self.clock = clock
        self._kept: dict[str, Remembered] = {}
        self._swept_at = clock()

    async def verify(self, secret: str) -> Verified | None:
        """From memory within the seconds, else from the database."""
        hashed = crypto.fingerprint(secret)
        moment = self.clock()
        kept = self._kept.get(hashed)
        if kept is not None and kept.until > moment:
            return kept.verified
        async with self.sessions() as session:
            verified = await verify_key(session, secret)
            await session.commit()
        if verified is None:
            self._kept.pop(hashed, None)
            return None
        until = moment + self.for_s
        expires_at = verified.key.expires_at
        if expires_at is not None:
            until = min(until, moment + max((expires_at - now()).total_seconds(), 0.0))
        self._kept[hashed] = Remembered(verified, until)
        self._sweep(moment)
        return verified

    def forget(self, *, fingerprint: str | None = None, subject: str | None = None) -> None:
        """Forget a key, or a member's keys, here and on every other gateway, now."""
        forgotten = Forgotten(fingerprint=fingerprint, subject=subject)
        self._forget(forgotten)
        self.signal.publish(FORGET_CHANNEL, forgotten.model_dump_json().encode())

    # Forgotten before the commit, a request with the key in between read its row still live and
    # remembered it for the seconds again: the revocation is committed first, then said.
    def forget_after_commit(
        self, session: AsyncSession, *, fingerprint: str | None = None, subject: str | None = None
    ) -> None:
        """Forget a key, or a member's keys, on every gateway once the session's transaction commits."""
        run_after_commit(session, lambda: self.forget(fingerprint=fingerprint, subject=subject))

    def hear(self, data: bytes) -> None:
        """Forget here what another gateway said to forget."""
        self._forget(Forgotten.model_validate_json(data))

    def clear(self) -> None:
        """Trust nothing remembered: every key is asked of the database again."""
        self._kept.clear()

    def _forget(self, forgotten: Forgotten) -> None:
        if forgotten.fingerprint is not None:
            self._kept.pop(forgotten.fingerprint, None)
        if forgotten.subject is not None:
            theirs = [h for h, kept in self._kept.items() if kept.verified.key.subject == forgotten.subject]
            for hashed in theirs:
                del self._kept[hashed]

    def _sweep(self, moment: float) -> None:
        if moment - self._swept_at < self.for_s:
            return
        self._swept_at = moment
        for hashed in [h for h, kept in self._kept.items() if kept.until <= moment]:
            del self._kept[hashed]
