"""The four-digit codes a caller keys to tie their call to a browser page, issued per agent."""

import asyncio
import contextlib
import secrets
import time
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from pinecall_runtime.calls.logs import Logs
from pinecall_runtime.calls.models import CallerCode
from pinecall_runtime.calls.repository.codes import CodeRepository
from pinecall_runtime.enums import CodeLog, Env
from pinecall_runtime.exceptions import QuotaExceeded, ServiceUnavailable
from pinecall_runtime.wire.events import CodeClaimed, CodeIssued
from pinecall_runtime.wire.parts import Projection

ISSUED = "code.issued"
CLAIMED = "code.claimed"

# Four digits to key on a phone; the cap per agent stops a page minting them by the thousand.
DIGITS = 4
LIVE_PER_AGENT = 50

# A call keys three codes at most: past them a code it keys ties it to no page, answered as one
# nobody issued, so a caller keying at random learns nothing and has three chances in all.
TRIES_PER_CALL = 3
A_DAY_S = 24 * 60 * 60.0

# Where a claim wakes the page waiting on the code, whichever gateway it waits on.
TAKEN_CHANNEL = "code:{agent}:{code}"


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


@dataclass(frozen=True)
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

    def __init__(self, logs: Logs) -> None:
        """Codes written on the logs, their wake-ups on the logs' signal."""
        self.logs = logs

    async def issue(self, session: AsyncSession, env: Env, agent: str, ttl_s: float, log: Projection) -> IssuedCode:
        """A new code for the agent, written on its log; at most fifty live at once."""
        codes = CodeRepository(session)
        await self._sweep(codes, agent, time.time())
        live = await codes.count_live(agent)
        if live >= LIVE_PER_AGENT:
            raise TooManyCodes(agent, live)
        expires_at = time.time() + ttl_s
        while True:
            code = _drawn()
            row = CallerCode(agent=agent, code=code, env=env, log=CodeLog(log), expires_at=expires_at)
            if await codes.keep(row):
                break
        issued = IssuedCode(code, env, agent, expires_at, log)
        await self.logs.agent(agent).append(
            ISSUED, CodeIssued(code=code, env=env, expires_at=expires_at, log=log).dump()
        )
        return issued

    async def status_of(self, session: AsyncSession, env: Env, agent: str, code: str) -> IssuedCode | None:
        """The code as it stands, once more after it expired; None for one nobody issued."""
        codes = CodeRepository(session)
        issued = _issued(await codes.get(agent, code))
        await self._sweep(codes, agent, time.time())
        return issued if issued is not None and issued.env is env else None

    # Listened for before the code is read again, so a claim between the two still wakes it.
    async def wait_for(self, session: AsyncSession, issued: IssuedCode, within_s: float) -> IssuedCode:
        """Wait up to that long for a call to key the code, and say how it stands."""
        channel = TAKEN_CHANNEL.format(agent=issued.agent, code=issued.code)
        codes = CodeRepository(session)
        if within_s > 0:
            with contextlib.suppress(ServiceUnavailable):
                taken = await self.logs.relay.signal.subscribe(channel)
                try:
                    now = _issued(await codes.get(issued.agent, issued.code))
                    if now is not None and now.claimed is None:
                        with contextlib.suppress(TimeoutError, StopAsyncIteration):
                            await asyncio.wait_for(anext(taken), within_s)
                finally:
                    taken.close()
        return _issued(await codes.get(issued.agent, issued.code)) or issued

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
        self.logs.relay.signal.publish(TAKEN_CHANNEL.format(agent=agent, code=code), b"taken")
        return _issued(row)

    # Swept as codes are asked for, not by a loop of its own.
    async def _sweep(self, codes: CodeRepository, agent: str, now: float) -> None:
        for code, claimed in await codes.expire(agent, now):
            if claimed is None:
                await self.logs.agent(agent).append(CLAIMED, CodeClaimed(code=code, call=None).dump())


def _issued(row: CallerCode | None) -> IssuedCode | None:
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


def _drawn() -> str:
    return f"{secrets.randbelow(10**DIGITS):0{DIGITS}d}"
