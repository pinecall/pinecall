"""The bodies of the fleet endpoints: each env's fleet and its floor, the fleet listed, and its demand."""

from pydantic import Field

from runtime.kit.schemas import Row, Schema
from runtime.wire.signal import WorkerStatus

A_FLEET_NAME = r"^[a-z0-9][a-z0-9-]{0,62}$"


class Fleets(Schema):
    """The fleet of workers each env's calls are dispatched to, as the operator named them."""

    production: str = Field(default="pinecall", pattern=A_FLEET_NAME)
    sandbox: str = Field(default="pinecall-sandbox", pattern=A_FLEET_NAME)


class Floors(Schema):
    """The scaled workers each env's fleet keeps warm whatever its calls; one left out is none."""

    production: int = Field(default=0, ge=0)
    sandbox: int = Field(default=0, ge=0)


# `seats` on the wire is a worker's slots: the console and the CLI of the release before 2026-11 read
# that word, so the field keeps it until they are gone, and is read off the value's `slots`.
class FleetTotals(Row):
    """One fleet over the workers heard from lately."""

    fleet: str
    workers: int
    active: int
    seats: int = Field(validation_alias="slots")
    free: int
    accepting: int
    full: bool
    # Rooms with a caller that no worker opened yet, offered by the gateway.
    waiting: int = 0


class FleetListed(Row):
    """GET /v1/ops/fleet: the box's time, every worker heard from, and each fleet summed."""

    now: float
    stale_after_s: float
    workers: list[WorkerStatus]
    totals: list[FleetTotals]


class FleetDemand(Row):
    """GET /v1/fleet/wanted: how many scaled workers the fleet wants, for KEDA."""

    fleet: str
    wanted: int
    # The fleet's calls and the slots its workers hold now, for whoever reads why; `seats` on the wire.
    active: int
    seats: int = Field(validation_alias="slots")
