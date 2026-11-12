"""The flows' loop: the clock that ends a run's sleep or its wait, and the look at the calls its runs placed."""

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from runtime.flows import service
from runtime.kit.loops import loop, survive

# A run wakes within this of its hour, and hears of its call's end within it.
WOKEN_EVERY_S = 2.0


# Every gateway passes: a run's row is held by the one that wakes it and skipped by the others. Each
# look is a transaction of its own: what one wakes, an app's process may take at once, and a look that
# fails never keeps the other from running. Until 2026-11 this was a `while True` the gateway started
# as a bare task, and one that died showed nowhere.
@loop("flow-wakes", every_s=WOKEN_EVERY_S)
async def wake_runs(sessions: async_sessionmaker[AsyncSession]) -> None:
    """One pass: the runs whose sleep or wait is over woken, then the runs whose call ended."""
    with survive("the waking of the runs whose sleep or wait is over"):
        async with sessions.begin() as session:
            await service.wake_due(session)
    with survive("the waking of the runs whose call ended"):
        async with sessions.begin() as session:
            await service.wake_called(session)
