"""The fleet's rules, one module per noun; what another domain uses is named here, and nothing else."""

from runtime.fleet.service.arrivals import forget_settled, offer_arrival
from runtime.fleet.service.dispatches import A_VISITOR_RETURNS_S, client_named_agent, dispatch_into, room_dispatch
from runtime.fleet.service.envs import Fleets, fleet_of, fleet_of_env, get_fleets
from runtime.fleet.service.offers import AN_AGENT_JOINS_WITHIN_S, Offering
from runtime.fleet.service.roster import Roster
from runtime.fleet.service.totals import totals_of

__all__ = [
    "AN_AGENT_JOINS_WITHIN_S",
    "A_VISITOR_RETURNS_S",
    "Fleets",
    "Offering",
    "Roster",
    "client_named_agent",
    "dispatch_into",
    "fleet_of",
    "fleet_of_env",
    "forget_settled",
    "get_fleets",
    "offer_arrival",
    "room_dispatch",
    "totals_of",
]
