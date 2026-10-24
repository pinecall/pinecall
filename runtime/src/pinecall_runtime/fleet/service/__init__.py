"""The fleet rules, one module per noun; what other domains use is named here once."""

from pinecall_runtime.fleet.schemas import (
    Fleets,
    FleetTotals,
    HeartbeatRequest,
    HeartbeatResponse,
    WorkerStatus,
)
from pinecall_runtime.fleet.service.arrivals import forget_settled, offer_arrival
from pinecall_runtime.fleet.service.demand import Demand, Line, wanted_scaled
from pinecall_runtime.fleet.service.envs import (
    env_of_fleet,
    fleet_of,
    fleet_of_env,
    fleets,
    set_fleets,
)
from pinecall_runtime.fleet.service.offers import AN_AGENT_JOINS_WITHIN_S, WAITING_COUNTED_S, Offering
from pinecall_runtime.fleet.service.rooms import (
    A_VISITOR_RETURNS_S,
    client_named_agent,
    close_room,
    dispatch_into,
    left_alone,
    livekit_event,
    room_dispatch,
    rooms_with_an_agent,
    seats_in,
)
from pinecall_runtime.fleet.service.roster import (
    HEARTBEAT_S,
    REFUSED_AT,
    STALE_AFTER_S,
    Roster,
    WorkerState,
    agent_name,
    heard_lately,
    overflow_name,
    worker_state,
)

__all__ = [
    "AN_AGENT_JOINS_WITHIN_S",
    "A_VISITOR_RETURNS_S",
    "HEARTBEAT_S",
    "REFUSED_AT",
    "STALE_AFTER_S",
    "WAITING_COUNTED_S",
    "Demand",
    "FleetTotals",
    "Fleets",
    "HeartbeatRequest",
    "HeartbeatResponse",
    "Line",
    "Offering",
    "Roster",
    "WorkerState",
    "WorkerStatus",
    "agent_name",
    "client_named_agent",
    "close_room",
    "dispatch_into",
    "env_of_fleet",
    "fleet_of",
    "fleet_of_env",
    "fleets",
    "forget_settled",
    "heard_lately",
    "left_alone",
    "livekit_event",
    "offer_arrival",
    "overflow_name",
    "room_dispatch",
    "rooms_with_an_agent",
    "seats_in",
    "set_fleets",
    "wanted_scaled",
    "worker_state",
]
