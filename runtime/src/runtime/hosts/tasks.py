"""The runner's loop: its beat to the gateway, and the hosts made what the gateway answers."""

import time

from runtime.hosts.service.runner import BEAT_S, Runner
from runtime.kit.loops import loop


@loop("runner-beat", every_s=BEAT_S)
async def beat(runner: Runner) -> None:
    """One beat of this env's runner."""
    await runner.beat_once(time.time())
