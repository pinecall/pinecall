"""The alerts endpoints: the env's monitors, the org's webhook set, read, dropped and proven, every alert kept."""

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Query

from pinecall_runtime.agents.auth import NO_SUCH_AGENT, TheRegistry
from pinecall_runtime.alerts import schemas, service
from pinecall_runtime.alerts.auth import EvalsKey, ProvidersKey, TheOperator
from pinecall_runtime.enums import Env
from pinecall_runtime.exceptions import NotFound
from pinecall_runtime.kit.auth import Actor
from pinecall_runtime.kit.handles import TheHandles
from pinecall_runtime.postgres import Session

router = APIRouter()

A_TEST_SAYS = {"said": "Pinecall reaches this URL; every alert of the org comes the same way."}


def _asked_by(actor: Actor) -> str:
    return actor.person.id if actor.person is not None else actor.key_id


# ── monitors ──


@router.get("/v1/monitors")
async def list_monitors(actor: EvalsKey, session: Session) -> schemas.MonitorList:
    """The env's monitors, oldest first, each with the last day it fired."""
    found = await service.list_monitors(session, actor.scope)
    return schemas.MonitorList(monitors=[schemas.MonitorRow.of(monitor) for monitor in found])


@router.post("/v1/monitors", status_code=201)
async def create_monitor(
    body: schemas.MonitorRequest, actor: EvalsKey, registry: TheRegistry, session: Session
) -> schemas.MonitorRow:
    """Watch a number: it fires, once a day, when it crosses the line over the window."""
    # A monitor of one agent watches an agent the org has; a slug typed wrong would never fire.
    if body.agent is not None and not await registry.is_known(actor.org, body.agent):
        raise NotFound(NO_SUCH_AGENT.format(slug=body.agent))
    return schemas.MonitorRow.of(await service.create_monitor(session, actor.scope, body, by=_asked_by(actor)))


@router.delete("/v1/monitors/{monitor_id}", status_code=204)
async def delete_monitor(monitor_id: str, actor: EvalsKey, session: Session) -> None:
    """Stop watching."""
    await service.delete_monitor(session, actor.scope, monitor_id)


# ── the webhook ──


@router.get("/v1/webhook")
async def get_webhook(actor: ProvidersKey, handles: TheHandles, session: Session) -> schemas.WebhookResponse | None:
    """The org's webhook and whether its posts are signed, never the secret; null when none."""
    found = await service.webhook_of(session, handles.vault, actor.org)
    return None if found is None else schemas.WebhookResponse(url=found.url, signed=found.secret is not None)


@router.put("/v1/webhook", status_code=204)
async def put_webhook(body: schemas.WebhookRequest, actor: ProvidersKey, handles: TheHandles, session: Session) -> None:
    """Keep the org's webhook; its alerts are posted there from the next one."""
    await service.put_webhook(
        session, handles.vault, actor.org, service.Webhook(url=body.url, secret=body.secret or None)
    )


@router.delete("/v1/webhook", status_code=204)
async def delete_webhook(actor: ProvidersKey, session: Session) -> None:
    """Forget the org's webhook; its alerts stay on the agents' logs from the next one."""
    await service.delete_webhook(session, actor.org)


# The one webhook endpoint that waits on the URL: a person watches whether it answered.
@router.post("/v1/webhook/test")
async def test_webhook(actor: ProvidersKey, handles: TheHandles, session: Session) -> schemas.WebhookTestResponse:
    """One test post, signed as every alert is, waited for: whether a 2xx came back."""
    webhook = await service.test_webhook(session, handles.vault, actor.org)
    sent = service.payload_of(actor.scope, None, service.A_TEST, dict(A_TEST_SAYS))
    error = await service.post_alert(handles.http, webhook, sent)
    return schemas.WebhookTestResponse(sent=error is None, error=error)


# ── the alerts kept ──

Limit = Annotated[int, Query(ge=1, le=service.MOST_READ)]


@router.get("/v1/alerts")
async def list_alerts(
    actor: ProvidersKey, session: Session, limit: Limit = service.READ, before: datetime | None = None
) -> schemas.AlertList:
    """The org's alerts in the key's env, newest first: kept whether or not they were mailed or posted."""
    found = await service.alerts_of(session, actor.scope, limit=limit, before=before)
    return schemas.AlertList(alerts=[schemas.AlertRow.model_validate(row, from_attributes=True) for row in found])


@router.get("/v1/ops/alerts")
async def list_every_orgs_alerts(
    _actor: TheOperator,
    session: Session,
    org: str | None = None,
    env: Env | None = None,
    limit: Limit = service.READ,
    before: datetime | None = None,
) -> schemas.AlertList:
    """Every org's alerts, or one org's, newest first: what broke for the box's tenants."""
    found = await service.every_orgs_alerts(session, org=org, env=env, limit=limit, before=before)
    return schemas.AlertList(alerts=[schemas.AlertRow.model_validate(row, from_attributes=True) for row in found])
