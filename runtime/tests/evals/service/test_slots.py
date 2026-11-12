"""A spoken simulation with no slot free waits for one, and says the fleet is full once."""

import pytest

from runtime.enums import Env
from runtime.evals.service.slots import wait_for_slot
from runtime.exceptions import ServiceUnavailable


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
