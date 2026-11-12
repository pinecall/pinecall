"""The live side's loops: the reaper's pass and the adoption, each one the process starts by its name."""

from runtime.live import tasks


# A part of a pass that fails is said and the other parts run, and the next pass comes: each part
# stands under `survive`, and a loop's passes under `kit.Loops`, which `tests/kit/test_loops.py` holds
# to it. Until 2026-11 the reaper was a `while True` of its own, and a pydantic error out of a log it
# could not read ended it on every gateway for good.
def test_the_reaper_passes_every_minute_and_the_adoption_every_second() -> None:
    assert (tasks.reap.name, tasks.reap.every_s) == ("reaper", 60.0)
    assert (tasks.adopt.name, tasks.adopt.every_s) == ("adoption", 1.0)
