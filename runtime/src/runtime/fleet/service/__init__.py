"""The fleet's rules, one module per noun; what another domain uses is named here, and nothing else."""

from runtime.fleet.service.arrivals import forget_settled, offer_arrival
from runtime.fleet.service.dispatches import A_VISITOR_RETURNS_S, dispatch_into
from runtime.fleet.service.envs import Fleets, fleet_of, fleet_of_env, get_fleets
from runtime.fleet.service.offers import Offering

__all__ = [
    "A_VISITOR_RETURNS_S",
    "Fleets",
    "Offering",
    "dispatch_into",
    "fleet_of",
    "fleet_of_env",
    "forget_settled",
    "get_fleets",
    "offer_arrival",
]
