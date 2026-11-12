"""Alerts' dependencies: the key that opens the monitors, and what raises an org's alerts."""

from typing import Annotated

from fastapi import Depends
from starlette.requests import HTTPConnection

from runtime.actor import Actor
from runtime.alerts.service.alerts import Alerting
from runtime.auth import Authenticator
from runtime.enums import KeyScope

# The monitors are read and set by who runs the evals; the webhook and the alerts by who holds the
# providers' key (`providers.auth.ProvidersKey`).
EvalsKey = Annotated[Actor, Depends(Authenticator(KeyScope.evals))]


# Built by the lifespan once the agents' logs exist to be handed in: every domain that raises an
# alert from a request asks for it here.
def alerting_of(connection: HTTPConnection) -> Alerting:
    """What raises an org's alerts, as the lifespan built it."""
    alerting: Alerting = connection.state.alerting
    return alerting


TheAlerting = Annotated[Alerting, Depends(alerting_of)]
