"""The bodies of the fleet endpoints: a worker's heartbeat, what the gateway answers, the fleet listed."""

from pydantic import ConfigDict, Field

from pinecall_runtime.kit.schemas import Schema
from pinecall_runtime.wire.base import WireModel

A_FLEET_NAME = r"^[a-z0-9][a-z0-9-]{0,62}$"


class HeartbeatRequest(WireModel):
    """A worker's report: its fleet, its name, what it holds and how loaded it is."""

    fleet: str
    worker: str
    # The name the worker registered under with LiveKit: the one a dispatch reaches it by; null
    # until LiveKit registered it, so no call is offered to a worker nobody can give it to.
    agent_name: str | None = None
    active: int
    # Measured slots; null when the worker is gated on its machine's CPU.
    max_jobs: int | None
    load: float
    draining: bool
    # Its last minute, as its calls' jobs told it; absent from a worker of an older release.
    ended: int | None = None
    failed: int | None = None
    errors: int | None = None
    turns: int | None = None
    first_audio_p95_s: float | None = None


class HeartbeatResponse(WireModel):
    """The answer to a heartbeat: whether this worker is cordoned, and its fleet full."""

    cordoned: bool
    full: bool


class FleetTotals(WireModel):
    """One fleet over the workers heard from lately."""

    fleet: str
    workers: int
    active: int
    seats: int
    free: int
    accepting: int
    full: bool
    # Rooms with a caller that no worker opened yet, offered by the gateway.
    waiting: int = 0


class WorkerStatus(WireModel):
    """One worker as its last heartbeat left it, and whether the operator cordoned it."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    fleet: str
    worker: str
    # The name the worker registered under with LiveKit: the one a dispatch reaches it by.
    agent_name: str | None = None
    active: int
    max_jobs: int | None
    load: float
    draining: bool
    cordoned: bool
    seen_at: float
    ended: int | None = None
    failed: int | None = None
    errors: int | None = None
    turns: int | None = None
    first_audio_p95_s: float | None = None


class Fleets(Schema):
    """The fleet of workers each env's calls are dispatched to, as the operator named them."""

    production: str = Field(default="pinecall", pattern=A_FLEET_NAME)
    sandbox: str = Field(default="pinecall-sandbox", pattern=A_FLEET_NAME)


class FleetListed(WireModel):
    """GET /v1/ops/fleet: the box's time, every worker heard from, and each fleet summed."""

    now: float
    stale_after_s: float
    workers: list[WorkerStatus]
    totals: list[FleetTotals]


class FleetDemand(WireModel):
    """GET /v1/fleet/wanted: how many scaled workers the fleet wants, for KEDA."""

    fleet: str
    wanted: int
    # The fleet's calls and the seats its workers hold now, for whoever reads why.
    active: int
    seats: int
