"""Fleet's dependencies: an env's fleet key, the roster and the dispatcher."""

from typing import Annotated

from fastapi import Depends
from starlette.requests import HTTPConnection

from runtime.actor import Actor
from runtime.auth import Authenticator
from runtime.enums import KeyScope
from runtime.fleet.service.offers import Offering
from runtime.fleet.service.roster import Roster

# An env's fleet key: the workers beat with it, and KEDA asks the demand with it. The middleware
# resolved it (the root's `the_fleet`, or a key of the old kind while a release still holds one).
FleetKey = Annotated[Actor, Depends(Authenticator(KeyScope.fleet))]


def roster_of(connection: HTTPConnection) -> Roster:
    """The roster the lifespan built."""
    roster: Roster = connection.state.roster
    return roster


def offering_of(connection: HTTPConnection) -> Offering:
    """The dispatcher the lifespan built."""
    offering: Offering = connection.state.offering
    return offering


TheRoster = Annotated[Roster, Depends(roster_of)]
TheOffering = Annotated[Offering, Depends(offering_of)]
