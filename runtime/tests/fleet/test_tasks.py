"""The fleet's two loops: declared under their names, and a pass of each on a real roster and offering."""

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from runtime.fleet import tasks
from runtime.fleet.service import slots
from runtime.fleet.service.offers import Offering
from runtime.fleet.service.roster import Roster
from tests.conftest import needs_the_database


# What keeps a loop going after a pass that raised is the process's `Loops` (tests/kit/test_loops.py):
# here, that the fleet's work is two of them, started by name.
def test_the_fleets_loops_are_declared_with_how_often_each_passes() -> None:
    assert (tasks.sweep_offers.name, tasks.sweep_offers.every_s) == ("offers", tasks.SWEPT_EVERY_S)
    assert (tasks.watch_roster.name, tasks.watch_roster.every_s) == ("roster", slots.HEARTBEAT_S)


async def test_a_pass_of_the_roster_on_a_gateway_that_heard_nobody_changes_nothing() -> None:
    changes: list[str] = []
    roster = Roster(on_change=lambda changed: changes.append(changed.worker))
    await tasks.watch_roster.each(roster)
    assert changes == []


@needs_the_database
async def test_a_pass_of_the_sweep_with_no_room_waiting_offers_none(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    await tasks.sweep_offers.each(Offering(sessions, servers={}, roster=Roster()))
