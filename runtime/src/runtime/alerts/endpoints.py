"""The alerts endpoints: the env's monitors, the org's webhook set, read, forgotten and proven, every alert kept."""

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Query

from runtime.agents.auth import TheOwners
from runtime.alerts import schemas
from runtime.alerts.auth import EvalsKey
from runtime.alerts.service import alerts, monitors, webhooks
from runtime.auth import TheOperator
from runtime.enums import Env
from runtime.handles import TheHttp, TheSessions, TheVault
from runtime.postgres import Session, TheBoxSession
from runtime.providers.auth import ProvidersKey

router = APIRouter()

Limit = Annotated[int, Query(ge=1, le=alerts.MOST_READ)]


# ── monitors ──


@router.get("/v1/monitors")
async def list_monitors(actor: EvalsKey, session: Session) -> schemas.MonitorList:
    """The env's monitors, oldest first, each with the last day it fired."""
    found = await monitors.list_monitors(session, actor.scope)
    return schemas.MonitorList(monitors=[schemas.MonitorRow.of(monitor) for monitor in found])


@router.post("/v1/monitors", status_code=201)
async def create_monitor(
    body: schemas.MonitorRequest, actor: EvalsKey, owners: TheOwners, session: Session
) -> schemas.MonitorRow:
    """Watch a number: it fires, once a day, when it crosses the line over the window."""
    made = await monitors.create_monitor(session, owners, actor.scope, body, body.agent, by=actor.asked_by)
    return schemas.MonitorRow.of(made)


@router.delete("/v1/monitors/{monitor_id}", status_code=204)
async def delete_monitor(monitor_id: str, actor: EvalsKey, session: Session) -> None:
    """Stop watching."""
    await monitors.delete_monitor(session, actor.scope, monitor_id)


# ── the webhook ──


@router.get("/v1/webhook")
async def get_webhook(actor: ProvidersKey, vault: TheVault, session: Session) -> schemas.WebhookResponse | None:
    """The org's webhook and whether its posts are signed, never the secret; null when none."""
    found = await webhooks.webhook_of(session, vault, actor.org)
    return None if found is None else schemas.WebhookResponse.of(found)


@router.put("/v1/webhook", status_code=204)
async def put_webhook(body: schemas.WebhookRequest, actor: ProvidersKey, vault: TheVault, session: Session) -> None:
    """Keep the org's webhook; its alerts are posted there from the next one. A URL into the box is refused."""
    await webhooks.put_webhook(session, vault, actor.org, webhooks.Webhook(url=body.url, secret=body.secret or None))


@router.delete("/v1/webhook", status_code=204)
async def delete_webhook(actor: ProvidersKey, session: Session) -> None:
    """Forget the org's webhook; its alerts stay on the agents' logs from the next one."""
    await webhooks.delete_webhook(session, actor.org)


# The one webhook endpoint that waits on the URL: a person watches whether it answered.
@router.post("/v1/webhook/test")
async def test_webhook(
    actor: ProvidersKey, sessions: TheSessions, vault: TheVault, http: TheHttp
) -> schemas.WebhookTestResponse:
    """One test post, signed as every alert is, waited for: whether a 2xx came back."""
    return schemas.WebhookTestResponse.of(await webhooks.test_webhook(sessions, vault, http, actor.scope))


# ── the alerts kept ──


@router.get("/v1/alerts")
async def list_alerts(
    actor: ProvidersKey, session: Session, limit: Limit = alerts.READ, before: datetime | None = None
) -> schemas.AlertList:
    """The org's alerts in the key's env, newest first: kept whether or not they were mailed or posted."""
    found = await alerts.list_alerts(session, actor.scope, limit=limit, before=before)
    return schemas.AlertList(alerts=[schemas.AlertRow.of(row) for row in found])


@router.get("/v1/ops/alerts")
async def list_every_orgs_alerts(
    _actor: TheOperator,
    session: TheBoxSession,
    org: str | None = None,
    env: Env | None = None,
    limit: Limit = alerts.READ,
    before: datetime | None = None,
) -> schemas.AlertList:
    """Every org's alerts, or one org's, newest first: what broke for the box's tenants."""
    found = await alerts.list_every_orgs_alerts(session, org=org, env=env, limit=limit, before=before)
    return schemas.AlertList(alerts=[schemas.AlertRow.of(row) for row in found])
