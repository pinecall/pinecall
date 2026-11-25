"""What the tests of the simulated callers share: the callers that wait for a process, one test's at a time."""

from collections.abc import AsyncIterator

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

THE_SUITES_CALLERS = text("select pg_advisory_lock(hashtext('tests:the callers that wait'))")
GIVEN_BACK = text("select pg_advisory_unlock(hashtext('tests:the callers that wait'))")
NOBODY_WAITS = text("delete from caller_jobs")


# A process claims the next caller that waits, whoever placed it, and every worker of the suite runs on
# the one database: a process a test builds would play the caller another test placed a moment before.
# A test that leaves a caller waiting, or builds a process, takes the callers to itself, as the fleets'
# seats are taken (`test_offers.py`).
@pytest.fixture
async def the_callers_to_itself(engine: AsyncEngine) -> AsyncIterator[None]:
    """Hold every caller that waits for a process for this test alone, until it ends."""
    async with engine.connect() as held:
        await held.execute(THE_SUITES_CALLERS)
        try:
            # Every test that leaves a caller waiting holds this lock: what is there is another one's,
            # over, and what this one leaves is cleared before the next.
            await held.execute(NOBODY_WAITS)
            await held.commit()
            yield
        finally:
            await held.execute(NOBODY_WAITS)
            await held.commit()
            await held.execute(GIVEN_BACK)
