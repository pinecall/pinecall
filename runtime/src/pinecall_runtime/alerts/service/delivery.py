"""An alert of the org's: on the agent's log, kept, mailed to its admins and the operators, posted to the webhooks."""

import hashlib
import hmac
import json
import logging
from typing import Protocol

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from pinecall_runtime.alerts.service.kept import keep_alert
from pinecall_runtime.alerts.service.telling import Mailer, mail_alert
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


class Alerting(Protocol):
    """What raising an alert reaches: the process's handles, the logs, the outbox (calls' Serving is one)."""

    @property
    def handles(self) -> Handles:
        """The vault, the HTTP client, the settings."""
        ...

    @property
    def logs(self) -> Logs:
        """The agents' own logs."""
        ...

    @property
    def outbox(self) -> Mailer:
        """Where an email is sent from."""
        ...


# Kept whatever else reaches: a webhook is an org's choice, and an alert nobody set one for is
# still mailed and still listed. The mail goes in the background; the posts are waited for.
async def raise_alert(
    session: AsyncSession, alerting: Alerting, scope: Scope, agent: str | None, alert: WireModel
) -> None:
    """On the agent's log when it is one agent's, kept, mailed, and posted to the org's webhook and the operator's."""
    kind, data = KIND_OF[type(alert)], alert.dump()
    handles = alerting.handles
    if agent is not None:
        await alerting.logs.agent(agent).append(kind, data)
    mailed = await mail_alert(session, alerting.outbox, handles.settings.address, scope, kind, data)
    await keep_alert(session, scope, agent, kind, data, mailed=mailed)
    payload = payload_of(scope, agent, kind, data)
    heard_by = (await webhook_of(session, handles.vault, scope.org), await operator_webhook_of(session, handles.vault))
    for webhook in heard_by:
        if webhook is None:
            continue
        error = await post_alert(handles.http, webhook, payload)
        if error is not None:
            logger.warning("org %s: %s was not delivered to %s: %s", scope.org, kind, webhook.url, error)


async def credits_exhausted(
    session: AsyncSession, alerting: Alerting, scope: Scope, agent: str, refused: QuotaExceeded
) -> None:
    """Say on the agent's log, and to the webhook, that one of the org's quotas ran out."""
    alert = CreditsExhausted.model_validate(
        {"org": scope.org, "quota": refused.quota, "used": refused.used, "limit": refused.limit}
    )
    await raise_alert(session, alerting, scope, agent, alert)


# Said in a transaction of its own: a request about to be refused rolls its own back, and an alert the
# refusal took with it was never kept — `pinecall alerts` did not list it, and the hourly mail, which
# looks for the one before it, was sent again with every refusal.
async def credits_refused(alerting: Alerting, scope: Scope, agent: str, refused: QuotaExceeded) -> None:
    """Say that a quota ran out as `credits_exhausted` does, for a refusal that is about to be raised."""
    async with alerting.handles.sessions.begin() as own:
        await credits_exhausted(own, alerting, scope, agent, refused)


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
