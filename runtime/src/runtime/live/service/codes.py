"""The four-digit codes a caller keys to tie their call to a browser page, issued per agent."""

import asyncio
import contextlib
import secrets
import time
from dataclasses import dataclass
from typing import Literal

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from runtime.calls.log import Logs
from runtime.enums import CodeLog, Env
from runtime.exceptions import NotFound, QuotaExceeded, ServiceUnavailable
from runtime.live.models import CallerCode
from runtime.live.peers import CODE_TAKEN, TAKEN
from runtime.live.repository import CodeRepository
from runtime.live.served import Served
from runtime.signal import Signal
from runtime.wire.events import CallClaimed, CodeClaimed, CodeIssued
from runtime.wire.parts import Projection

ISSUED = "code.issued"
CLAIMED = "code.claimed"

# Four digits to key on a phone; the cap per agent stops a page minting them by the thousand.
DIGITS = 4
LIVE_PER_AGENT = 50

# A call keys three codes at most: past them a code it keys ties it to no page, answered as one
# nobody issued, so a caller keying at random learns nothing and has three chances in all.
TRIES_PER_CALL = 3
A_DAY_S = 24 * 60 * 60.0
MOST_DRAWS = 20


class TooManyCodes(QuotaExceeded):
    """The agent has as many codes waiting as it may."""

    def __init__(self, agent: str, live: int) -> None:
        super().__init__(
            f"agent {agent} already has {live} codes waiting for a call: let one be claimed or expire before "
            f"issuing another",
            quota="codes",
            used=live,
            limit=LIVE_PER_AGENT,
        )


# One sentence, whoever asks: the worker whose caller keyed it, the app whose agent heard it, the page
# that waits on it. Until 2026-11 the same refusal was written three ways, in three modules.
class NoSuchCode(NotFound):
    """No page waits on the code: nobody issued it, it expired, a call took it, or the call is out of tries."""

    def __init__(self, code: str, agent: str) -> None:
        super().__init__(
            f"no code {code} is waiting for agent {agent}: nobody issued it, it expired, or a call took it"
        )


@dataclass(frozen=True, slots=True)
class IssuedCode:
    """A code a page shows, waiting for the call that keys it, and the call once one did."""

    code: str
    env: Env
    agent: str
    expires_at: float
    log: Projection
    claimed: str | None = None


# Kept in Postgres, so any gateway issues, claims and answers a code; written on each agent's
# log as code.issued and code.claimed (no call: it expired). A code is the agent's, whatever the env.
class Codes:
    """Every agent's live caller codes, and a waiting page's wake-up for each."""

    def __init__(self, sessions: async_sessionmaker[AsyncSession], logs: Logs, signal: Signal) -> None:
        """Codes written on the logs, their wake-ups on the signal, a page's asks on sessions of their own."""
        self.sessions = sessions
        self.logs = logs
        self.signal = signal

    async def issue(self, session: AsyncSession, env: Env, agent: str, ttl_s: float, log: Projection) -> IssuedCode:
        """A new code for the agent, written on its log; at most fifty live at once."""
        codes = CodeRepository(session)
        await self._sweep(codes, agent, time.time())
        live = await codes.count_live(agent)
        if live >= LIVE_PER_AGENT:
            raise TooManyCodes(agent, live)
        expires_at = time.time() + ttl_s
        code = await self._keep_new(codes, env, agent, CodeLog(log), expires_at)
        issued = IssuedCode(code, env, agent, expires_at, log)
        await self.logs.agent(agent).append(
            ISSUED, CodeIssued(code=code, env=env, expires_at=expires_at, log=log).dump()
        )
        return issued

    # A page's ask is answered on a session of its own, given back before anything is waited for:
    # until 2026-11 the ask read through the request's session and then waited up to 25 s for the
    # signal with that transaction open, and eight pages waiting emptied the endpoints' pool.
    async def find_status(self, env: Env, agent: str, code: str) -> IssuedCode | None:
        """The code as it stands, once more after it expired; None for one nobody issued."""
        async with self.sessions.begin() as session:
            codes = CodeRepository(session)
            issued = _read(await codes.find(agent, code))
            await self._sweep(codes, agent, time.time())
        return issued if issued is not None and issued.env is env else None

    # Listened for before the code is read again, so a claim between the two still wakes it. No
    # connection is held while it waits: each read is a session opened and given back.
    async def wait_for_claim(self, issued: IssuedCode, within_s: float) -> IssuedCode:
        """Wait up to that long for a call to key the code, and say how it stands."""
        if within_s > 0:
            with contextlib.suppress(ServiceUnavailable):
                taken = await CODE_TAKEN.subscribe(self.signal, agent=issued.agent, code=issued.code)
                try:
                    now = await self._find(issued.agent, issued.code)
                    if now is not None and now.claimed is None:
                        with contextlib.suppress(TimeoutError, StopAsyncIteration):
                            await asyncio.wait_for(anext(taken), within_s)
                finally:
                    taken.close()
        return await self._find(issued.agent, issued.code) or issued

    async def claim(self, session: AsyncSession, env: Env, agent: str, code: str, call: str) -> IssuedCode | None:
        """Tie the code to the call that keyed it; None if nobody's, dead, taken, or a 4th try."""
        codes = CodeRepository(session)
        now = time.time()
        await self._sweep(codes, agent, now)
        # A try refused stays counted.
        await codes.forget_tries_before(now - A_DAY_S)
        if await codes.count_try(call, now) > TRIES_PER_CALL:
            return None
        row = await codes.take(agent, code, env, call, now)
        if row is None:
            return None
        await self.logs.agent(agent).append(CLAIMED, CodeClaimed(code=code, call=call).dump())
        CODE_TAKEN.tell(self.signal, TAKEN, agent=agent, code=code)
        return _read(row)

    # What an app's socket is given to answer `call.claim` with (`socket.ClaimCode`): the app says its
    # own refusal when no page waits.
    async def claim_heard(self, session: AsyncSession, served: Served, code: str) -> bool:
        """Tie the call to the page showing the code its agent heard; False when no page waits on it."""
        return await claim_code(session, self, served, code, via="agent")

    # At most fifty of an agent's ten thousand codes are live, so a draw meets one of them once in two
    # hundred: a handful of draws always finds a free one.
    async def _keep_new(self, codes: CodeRepository, env: Env, agent: str, log: CodeLog, expires_at: float) -> str:
        for _ in range(MOST_DRAWS):
            code = _draw()
            if await codes.keep(CallerCode(agent=agent, code=code, env=env, log=log, expires_at=expires_at)):
                return code
        raise ServiceUnavailable(f"no free code was drawn for agent {agent} in {MOST_DRAWS} draws: ask again")

    async def _find(self, agent: str, code: str) -> IssuedCode | None:
        async with self.sessions() as session:
            return _read(await CodeRepository(session).find(agent, code))

    # Swept as codes are asked for, not by a loop of its own.
    async def _sweep(self, codes: CodeRepository, agent: str, now: float) -> None:
        for code, claimed in await codes.expire(agent, now):
            if claimed is None:
                await self.logs.agent(agent).append(CLAIMED, CodeClaimed(code=code, call=None).dump())


async def claim_code(
    session: AsyncSession, codes: Codes, served: Served, code: str, *, via: Literal["keypad", "agent"]
) -> bool:
    """Tie the call to the page showing the code; False when no page waits on it."""
    issued = await codes.claim(session, served.scope.env, served.agent, code, served.call)
    if issued is None:
        return False
    await served.log.append("call.claimed", CallClaimed(code=code, via=via).dump())
    return True


# A code nobody issued is a 404, and an ordinary one: the caller may be dialling an extension.
async def claim_keyed_code(session: AsyncSession, codes: Codes, served: Served, code: str) -> None:
    """The caller keyed a page's code: tie the call to it, or refuse it as a code nobody waits on."""
    if not await claim_code(session, codes, served, code, via="keypad"):
        raise NoSuchCode(code, served.agent)


def _read(row: CallerCode | None) -> IssuedCode | None:
    if row is None:
        return None
    return IssuedCode(
        code=row.code,
        env=row.env,
        agent=row.agent,
        expires_at=row.expires_at,
        log="tenant" if row.log is CodeLog.tenant else "public",
        claimed=row.claimed,
    )


def _draw() -> str:
    return f"{secrets.randbelow(10**DIGITS):0{DIGITS}d}"
