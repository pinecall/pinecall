"""The fleet's loops go on after a pass that raised, whatever it raised, and say how many failed."""

import dataclasses
from typing import cast

from runtime.fleet import tasks
from runtime.fleet.service.offers import Offering
from runtime.fleet.service.roster import Roster
from runtime.kit.loops import Bound, Loops
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


class Looking:
    """A roster whose first look for silent workers raises."""

    def __init__(self) -> None:
        """No look yet."""
        self.looks: list[float] = []

    def forget_silent(self, now: float) -> None:
        """Raise the first time, look after."""
        self.looks.append(now)
        if len(self.looks) == 1:
            raise RuntimeError("the feed could not be told")


def fast(bound: Bound) -> Bound:
    """The loop passing as often as a test can wait for."""
    return dataclasses.replace(bound, every_s=0.01)


# The sweep once caught PinecallError, TwirpError, OSError and SQLAlchemyError, and a pydantic error
# out of a room's dispatch ended it for good: no room was offered again on that gateway.
async def test_a_sweep_that_raises_anything_does_not_end_the_loop() -> None:
    offering = Sweeping()
    running = Loops()
    running.start(fast(tasks.sweep_offers.bind(cast(Offering, offering))))
    try:
        await until(lambda: offering.swept >= 3)
        [beat] = running.beats()
        assert (beat.name, beat.alive, beat.failures) == ("offers", True, 1)
    finally:
        await running.stop()


async def test_a_look_for_silent_workers_that_raises_does_not_end_the_tick() -> None:
    roster = Looking()
    running = Loops()
    running.start(fast(tasks.watch_roster.bind(cast(Roster, roster))))
    try:
        await until(lambda: len(roster.looks) >= 3)
        [beat] = running.beats()
        assert (beat.name, beat.alive, beat.failures) == ("roster", True, 1)
    finally:
        await running.stop()
