"""The fleet's rules, one module per noun; what another domain uses is named here, and nothing else."""

from runtime.fleet.service.dispatches import A_VISITOR_RETURNS_S, dispatch_into
from runtime.fleet.service.envs import Fleets, fleet_of, fleet_of_env, get_fleets

__all__ = ["A_VISITOR_RETURNS_S", "Fleets", "dispatch_into", "fleet_of", "fleet_of_env", "get_fleets"]
