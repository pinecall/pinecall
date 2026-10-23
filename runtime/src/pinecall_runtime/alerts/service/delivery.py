"""An alert of the org's: written on the agent's log, then posted to the org's webhook and the operator's."""

import hashlib
import hmac
import json
import logging
from typing import Protocol

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from pinecall_runtime.alerts.service.webhooks import Webhook, operator_webhook_of, webhook_of
from pinecall_runtime.exceptions import QuotaExceeded
from pinecall_runtime.kit.auth import Scope
from pinecall_runtime.kit.handles import Handles
from pinecall_runtime.kit.text import JsonObject
from pinecall_runtime.kit.time import epoch
from pinecall_runtime.wire.base import WireModel
from pinecall_runtime.wire.events import CreditsExhausted, MonitorFired, SpendUnusual
from pinecall_runtime.wire.feed import AppFailed

logger = logging.getLogger(__name__)

# Once, and once again on a connection error or a 5xx: an alert is said once a day, so a URL that
# is down for a minute is told twice and then the log holds it alone.
ATTEMPTS = 2
# A post waits this long for a 2xx; the seal of a call is behind it.
WAITS_S = 5.0
EVENT_HEADER = "x-pinecall-event"
SIGNATURE_HEADER = "x-pinecall-signature"
A_TEST = "webhook.test"
A_SERVER_ERROR = 500
# The alerts, each under the type the agent's log writes it as; an app's names no agent.
KIND_OF: dict[type[WireModel], str] = {
    MonitorFired: "monitor.fired",
    SpendUnusual: "spend.unusual",
    CreditsExhausted: "credits.exhausted",
    AppFailed: "app.failed",
}


class AgentLog(Protocol):
    """One agent's log, as an alert is written on it."""

    async def append(self, kind: str, data: JsonObject | None = None) -> object:
        """One entry on the log."""
        ...


class Logs(Protocol):
    """The logs an alert is written to: calls' are above alerts, so they are handed in."""

    def agent(self, slug: str) -> AgentLog:
        """The agent's own log."""
        ...


async def raise_alert(
    session: AsyncSession, handles: Handles, logs: Logs, scope: Scope, agent: str | None, alert: WireModel
) -> None:
    """Write the alert on the agent's log, when it is one agent's; post it to the org's webhook and the operator's."""
    kind, data = KIND_OF[type(alert)], alert.dump()
    if agent is not None:
        await logs.agent(agent).append(kind, data)
    payload = payload_of(scope, agent, kind, data)
    heard_by = (await webhook_of(session, handles.vault, scope.org), await operator_webhook_of(session, handles.vault))
    for webhook in heard_by:
        if webhook is None:
            continue
        error = await post_alert(handles.http, webhook, payload)
        if error is not None:
            logger.warning("org %s: %s was not delivered to %s: %s", scope.org, kind, webhook.url, error)


async def credits_exhausted(
    session: AsyncSession, handles: Handles, logs: Logs, scope: Scope, agent: str, refused: QuotaExceeded
) -> None:
    """Say on the agent's log, and to the webhook, that one of the org's quotas ran out."""
    alert = CreditsExhausted.model_validate(
        {"org": scope.org, "quota": refused.quota, "used": refused.used, "limit": refused.limit}
    )
    await raise_alert(session, handles, logs, scope, agent, alert)


async def post_alert(http: httpx.AsyncClient, webhook: Webhook, sent: JsonObject) -> str | None:
    """Post the payload, again on a connection error or a 5xx; None on a 2xx, else why not."""
    body = json.dumps(sent, separators=(",", ":")).encode()
    headers = {"content-type": "application/json", EVENT_HEADER: str(sent["type"])}
    if webhook.secret is not None:
        digest = hmac.new(webhook.secret.encode(), body, hashlib.sha256).hexdigest()
        headers[SIGNATURE_HEADER] = f"sha256={digest}"
    error = "never posted"
    for _ in range(ATTEMPTS):
        try:
            answer = await http.post(webhook.url, content=body, headers=headers, timeout=WAITS_S)
        except httpx.HTTPError as unreachable:
            error = f"{type(unreachable).__name__}: {unreachable}"
            continue
        if answer.is_success:
            return None
        error = f"HTTP {answer.status_code}"
        if answer.status_code < A_SERVER_ERROR:
            return error
    return error


def payload_of(scope: Scope, agent: str | None, kind: str, data: JsonObject) -> JsonObject:
    """What a post carries: the kind, whose env it is, the agent, when, and the alert itself."""
    return {"type": kind, "org": scope.org, "env": scope.env, "agent": agent, "at": epoch(), "data": data}
