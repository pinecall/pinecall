"""A call sealed by hand: its head claimed in a sandbox and its entries folded into the day, as the seal does."""

import time
from collections.abc import Sequence

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from pinecall_runtime.calls.models import CallLogHead
from pinecall_runtime.calls.service import drift
from pinecall_runtime.enums import Env
from pinecall_runtime.wire.base import Entry
from pinecall_runtime.wire.scores import CallScore

NOT_JUDGED = CallScore(judges=[], judge_calls=0)


async def opened(sessions: async_sessionmaker[AsyncSession], org: str, call: str, agent: str) -> None:
    """A sealed head for the call, claimed in the org's sandbox and started now, as a fold finds it."""
    async with sessions.begin() as session:
        session.add(
            CallLogHead(
                log=call,
                call=call,
                agent=agent,
                org=org,
                env=Env.sandbox,
                holder="",
                sealed=True,
                started_at=time.time(),
                config_version=1,
            )
        )


async def fold_call(
    sessions: async_sessionmaker[AsyncSession],
    org: str,
    entries: Sequence[Entry],
    *,
    score: CallScore = NOT_JUDGED,
) -> str:
    """Open the entries' call in the org's sandbox and fold it into its day; the call."""
    first = entries[0]
    assert first.call is not None
    await opened(sessions, org, first.call, first.agent)
    async with sessions.begin() as session:
        assert await drift.fold(session, first.call, entries, score)
    return first.call
