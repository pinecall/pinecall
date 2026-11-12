"""A worker's report to its gateway: what it holds, its last minute, a cordon's way out, and the names it goes by."""

import asyncio
import logging
import socket
import time

from runtime.exceptions import UpstreamError
from runtime.fleet import service as fleet
from runtime.jobs.service.client import GatewayClient
from runtime.jobs.service.load import Load, Server
from runtime.jobs.service.measures import LastMinute
from runtime.wire.worker import HeartbeatRequest

logger = logging.getLogger(__name__)

# A worker that starts again under the same name (a pod's container, after its node was reset)
# registers anew while LiveKit may hold the last process's dead socket for 15-20 minutes and offer
# it calls. This process's start, to the second, keeps the two apart; the roster keys by the
# worker's name, so the gateway offers only the newest registration.
STARTED = f"{time.time():.0f}"

# The id livekit's AgentServer holds until LiveKit answers its registration with the real one.
UNREGISTERED = "unregistered"

# The exit a cordoned worker leaves with; its unit's RestartPreventExitStatus= keeps it down.
CORDONED_EXIT = 3


class Heartbeats:
    """The worker's report to its gateway every five seconds, and a cordon's way out."""

    def __init__(
        self,
        server: Server,
        gateway: GatewayClient,
        minute: LastMinute,
        load: Load,
        *,
        fleet_name: str,
        worker: str,
    ) -> None:
        """Not beating yet; `leave` is set when the worker must go."""
        self.server = server
        self.gateway = gateway
        self.minute = minute
        # The same measure livekit reads this worker by, asked here for the number alone.
        self.load = load
        self.fleet = fleet_name
        self.name = worker
        self.agent_name = agent_name_of(fleet_name, worker)
        self.cordoned = False
        self.leave = asyncio.Event()
        # Set once LiveKit registered the worker and the gateway answered a heartbeat uncordoned.
        self.ready = asyncio.Event()

    def beat(self) -> HeartbeatRequest:
        """What this worker holds now, and what its calls did in the last minute."""
        active = len(self.server.active_jobs)
        last = self.minute.read_minute(asyncio.get_running_loop().time())
        # The name only once LiveKit registered it: before, a call offered to it waits for nobody.
        is_registered = self.server.id != UNREGISTERED
        return HeartbeatRequest(
            fleet=self.fleet,
            worker=self.name,
            agent_name=self.agent_name if is_registered else None,
            active=active,
            max_jobs=self.load.max_jobs,
            load=self.read_load(active),
            draining=self.server.draining,
            ended=last.ended,
            failed=last.failed,
            errors=last.errors,
            turns=last.turns,
            first_audio_p95_s=last.first_audio_p95_s,
        )

    # The gateway's scale: calls over slots, full at 1.0; a worker on CPU reports the share LiveKit
    # reads, which is the same number on both scales.
    def read_load(self, active: int) -> float:
        """The load the gateway reads for this worker."""
        slots = self.load.max_jobs
        return active / slots if slots is not None else self.load.read(self.server)

    # A gateway away is said and waited out: the worker keeps its calls meanwhile. A cordoned worker
    # is asked to leave once and goes on beating while it drains: until 2026-11 it stopped, and the
    # gateway forgot a worker that still held calls.
    async def tell(self) -> None:
        """One beat: report the worker, and ask it to leave the first time the gateway says it is cordoned."""
        try:
            answered = await self.gateway.beat(self.beat())
        except UpstreamError as refused:
            logger.warning("heartbeat: %s", refused)
            return
        if answered.cordoned and not self.cordoned:
            logger.warning("cordoned by the gateway: draining, then leaving")
            self.cordoned = True
            self.leave.set()
        if not answered.cordoned and self.server.id != UNREGISTERED:
            self.ready.set()


# systemd's Type=notify: `systemctl restart` returns only once this is said, so a release starts
# the next instance only after this one can take calls. Outside systemd there is nobody to tell.
async def announce_ready(beats: Heartbeats, notify: str | None) -> bool:
    """Tell systemd the worker is ready once LiveKit registered it and the gateway heard it."""
    await beats.ready.wait()
    if not notify:
        return False
    # An address that starts with @ is in the abstract namespace, whose first byte is a zero.
    address = "\0" + notify[1:] if notify.startswith("@") else notify
    with socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM) as systemd:
        systemd.connect(address)
        systemd.sendall(b"READY=1")
    logger.info("registered with LiveKit and heard by the gateway: ready")
    return True


# The job's process names its call's worker as the heartbeat does: the same setting, the same host.
def worker_name_of(named: str | None) -> str:
    """What the worker is called in its heartbeats and its calls: its setting, or the short host."""
    return named or socket.gethostname().split(".")[0]


# Its own name, not the fleet's: LiveKit offers a job only to the workers registered under the
# name a dispatch carries, so the gateway reaches this process and no other (docs/scaling.md).
def agent_name_of(fleet_name: str, worker: str) -> str:
    """The name the worker registers under with LiveKit: its fleet's, its own, its start."""
    return f"{fleet.agent_name(fleet_name, worker)}.{STARTED}"
