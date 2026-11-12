"""Hosting's loop: the meter, which counts the time each env's apps served."""

from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from runtime.enums import Env
from runtime.hosting.service import usage
from runtime.hosting.service.apps import Processes
from runtime.kit.loops import loop, survive

# How often the time served is counted: an app that stops serving is counted up to the last pass.
COUNTED_EVERY_S = 5.0


# Every gateway counts, with or without a runner beating: the statement locks the apps it counts, so two
# gateways at once count no span twice. Until 2026-11 the count ran inside the runner's heartbeat, and an
# env with no runner (a server that runs none, an org's agents built in the console) was never counted.
@loop("hosting-meter", every_s=COUNTED_EVERY_S)
async def count_serving(sessions: async_sessionmaker[AsyncSession], processes: Processes) -> None:
    """One pass: in each env, the time its serving apps served since the last count."""
    for env in Env:
        with survive("the count of the time an env's apps served", env.value):
            async with sessions.begin() as session:
                await usage.count_serving(session, processes, env, datetime.now(UTC))
