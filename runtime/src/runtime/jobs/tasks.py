"""The worker's loop: its heartbeat to the gateway."""

from runtime.fleet import service as fleet
from runtime.jobs.service.heartbeat import Heartbeats
from runtime.kit.loops import loop


# A beat the gateway did not take is said by the beat itself and the next is made on time: a worker
# that stopped beating is a worker the gateway forgets, still holding its calls.
@loop("worker-heartbeat", every_s=fleet.HEARTBEAT_S)
async def beat(beats: Heartbeats) -> None:
    """One heartbeat of this worker."""
    await beats.tell()
