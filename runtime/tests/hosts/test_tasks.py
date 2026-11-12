"""The runner's loop: one beat every few seconds, by the name the process starts it under."""

from runtime.hosts import tasks
from runtime.hosts.service.runner import BEAT_S


# A beat that meets anything does not end the runner: a gateway away is the beat's own to say
# (`tests/hosts/service/test_runner.py`), and whatever else a pass raises is `kit.Loops`' to survive.
def test_the_runner_beats_on_a_loop_the_process_starts() -> None:
    assert (tasks.beat.name, tasks.beat.every_s) == ("runner-beat", BEAT_S)
