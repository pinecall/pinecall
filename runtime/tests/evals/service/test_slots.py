"""A spoken simulation with no slot free waits for one, and says the fleet is full once."""

from typing import cast

import pytest
from sqlalchemy.exc import OperationalError
from sqlalchemy.exc import TimeoutError as PoolTimeout

from runtime.enums import Env
from runtime.evals.service.slots import ask_for_seat, wait_for_slot
from runtime.exceptions import ServiceUnavailable
from runtime.fleet import service as fleet
from runtime.wire.dispatch import Dispatch


async def test_a_spoken_simulation_waits_for_a_seat_and_says_the_fleet_is_full_once() -> None:
    """No seat for two asks, then one: the wait ends, and the fleet was said full one time."""
    answers = iter([False, False, True])
    told: list[str] = []

    async def asks() -> bool:
        return next(answers)

    async def full() -> None:
        told.append("fleet.full")

    waited = await wait_for_slot(asks, full, env=Env.sandbox, within_s=5.0, every_s=0.01)
    assert told == ["fleet.full"] and 0.0 < waited < 1.0


async def test_a_spoken_simulation_gives_up_on_a_seat_in_time() -> None:
    """Every ask refused past the wait: the simulation does not start, and the sentence says how long it waited."""

    async def never() -> bool:
        return False

    async def full() -> None:
        pass

    with pytest.raises(ServiceUnavailable, match="every seat of the sandbox's fleet held a call for 0 s"):
        await wait_for_slot(never, full, env=Env.sandbox, within_s=0.0, every_s=0.01)


class ADispatcher:
    """A fleet's dispatcher whose database refuses the asks it is told to, and seats the room at the others."""

    def __init__(self, *refusals: Exception) -> None:
        self.refusals = list(refusals)
        self.asked = 0

    async def take_seat(self, room: str, _fleet: str, _dispatch: Dispatch) -> fleet.Seat | None:
        self.asked += 1
        if self.refusals:
            raise self.refusals.pop(0)
        return fleet.Seat(room)


# 2026-11-25: a caller asks for its seat every two seconds for as long as it waits, forty-five minutes
# at most. One ask that found the gateway's pool full raised, and the caller's task ended with it.
async def test_an_ask_that_finds_no_connection_free_is_a_seat_not_got_this_time_and_any_other_failure_is_raised() -> (
    None
):
    busy = ADispatcher(PoolTimeout("QueuePool limit of size 8 overflow 0 reached"))
    offering, dispatch = cast(fleet.Offering, busy), Dispatch(agent="recepcion")
    assert await ask_for_seat(offering, "room_1", "sandbox", dispatch) is None
    assert await ask_for_seat(offering, "room_1", "sandbox", dispatch) == fleet.Seat("room_1")
    assert busy.asked == 2
    down = cast(fleet.Offering, ADispatcher(OperationalError("select 1", {}, Exception("the server closed"))))
    with pytest.raises(OperationalError):
        await ask_for_seat(down, "room_1", "sandbox", dispatch)
