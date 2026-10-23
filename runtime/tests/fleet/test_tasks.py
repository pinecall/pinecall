"""The fleet's loops go on after a pass that raised, whatever it raised."""

import asyncio
from typing import cast

import pytest

from pinecall_runtime.fleet import tasks
from pinecall_runtime.fleet.service.offers import Offering
from pinecall_runtime.fleet.service.roster import Roster
from tests.conftest import until


class Sweeping:
    """An offering whose first sweep raises what no list of classes would have caught."""

    def __init__(self) -> None:
        """No sweep yet."""
        self.swept = 0

    async def sweep(self) -> list[str]:
        """Raise the first time, answer after."""
        self.swept += 1
        if self.swept == 1:
            raise ValueError("1 validation error for Dispatch\nagent\n  Field required")
        return []


# The sweep once caught PinecallError, TwirpError, OSError and SQLAlchemyError, and a pydantic error
# out of a room's dispatch ended it for good: no room was offered again on that gateway.
async def test_a_sweep_that_raises_anything_does_not_end_the_loop(monkeypatch: pytest.MonkeyPatch) -> None:
    offering = Sweeping()
    monkeypatch.setattr(tasks, "SWEPT_EVERY_S", 0.01)
    sweeping = asyncio.create_task(tasks.sweep_offers(cast(Offering, offering)))
    try:
        await until(lambda: offering.swept >= 3)
        assert not sweeping.done()
    finally:
        sweeping.cancel()
        await asyncio.gather(sweeping, return_exceptions=True)


async def test_a_look_for_silent_workers_that_raises_does_not_end_the_tick(monkeypatch: pytest.MonkeyPatch) -> None:
    looks: list[float] = []

    class Looking:
        def forget_silent(self, now: float) -> None:
            looks.append(now)
            if len(looks) == 1:
                raise RuntimeError("the feed could not be told")

    monkeypatch.setattr(tasks, "HEARTBEAT_S", 0.01)
    ticking = asyncio.create_task(tasks.watch_roster(cast(Roster, Looking())))
    try:
        await until(lambda: len(looks) >= 3)
        assert not ticking.done()
    finally:
        ticking.cancel()
        await asyncio.gather(ticking, return_exceptions=True)
