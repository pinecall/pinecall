"""The loops alerts owns: the alerts that wait posted to their webhooks, and the newborns' sweep every hour."""

import httpx
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from runtime.alerts.service import newborns, webhooks
from runtime.alerts.service.alerts import Alerting
from runtime.kit.crypto import Vault
from runtime.kit.loops import loop

# An alert reaches its webhooks within this of being raised: its row waits for the next pass.
POSTED_EVERY_S = 5.0
# How often a gateway sweeps; the claim on the org keeps two gateways from saying it twice.
SWEPT_EVERY_S = 3600.0


# Every gateway passes: a row is taken by one of them alone. A pass that fails is said and the next
# one runs, so a database that was away for a minute posts what waited once it is back.
@loop("alert-posts", every_s=POSTED_EVERY_S)
async def post_alerts(sessions: async_sessionmaker[AsyncSession], vault: Vault, http: httpx.AsyncClient) -> None:
    """Post every alert that waits for it to the org's webhook and the operator's."""
    await webhooks.post_pending(sessions, vault, http)


# Until 2026-11 this loop was a `while True` in the service, started by the gateway as a bare task.
@loop("newborns", every_s=SWEPT_EVERY_S)
async def sweep_newborns(
    sessions: async_sessionmaker[AsyncSession], alerting: Alerting, ended_calls: newborns.EndedCalls
) -> None:
    """A sweep of the newborn orgs now, and one every hour."""
    await newborns.watch_newborns(sessions, alerting, ended_calls)
