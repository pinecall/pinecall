"""An alert raised: on the agent's log when it is one agent's, and posted to the org's webhook either way."""

import json
import os

import httpx
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from pinecall_runtime.alerts.service.delivery import raise_alert
from pinecall_runtime.alerts.service.webhooks import Webhook, put_webhook
from pinecall_runtime.config import load_settings
from pinecall_runtime.enums import Env
from pinecall_runtime.kit.auth import Scope
from pinecall_runtime.kit.crypto import Vault
from pinecall_runtime.kit.handles import Handles
from pinecall_runtime.kit.text import JsonObject
from pinecall_runtime.redis import LocalSignal
from pinecall_runtime.wire.feed import AppFailed
from tests.conftest import Tenant, needs_the_database
from tests.fakes.livekit import per_world
from tests.fakes.webhooks import Receiver

VAULT = Vault(os.environ["PINECALL_VAULT_KEY"])


class WrittenLogs:
    """The agents' logs as the alert sees them: every entry appended, by agent."""

    def __init__(self) -> None:
        """No agent written yet."""
        self.written: list[tuple[str, str, JsonObject | None]] = []

    def agent(self, slug: str) -> "WrittenLogs.Log":
        """The agent's own log."""
        return WrittenLogs.Log(self, slug)

    class Log:
        """One agent's log, appending into the record."""

        def __init__(self, logs: "WrittenLogs", slug: str) -> None:
            """The log of one agent."""
            self.logs, self.slug = logs, slug

        async def append(self, kind: str, data: JsonObject | None = None) -> object:
            """One entry kept."""
            self.logs.written.append((self.slug, kind, data))
            return None


@needs_the_database
async def test_an_apps_alert_is_posted_to_the_webhook_with_no_agent_and_written_on_no_log(
    sessions: async_sessionmaker[AsyncSession], tenant: Tenant
) -> None:
    receiver, logs = Receiver(), WrittenLogs()
    async with sessions.begin() as session:
        await put_webhook(session, VAULT, tenant.org, Webhook(url=receiver.url))
    failed = AppFailed(app="support", host="support-r4-e8033b63", release=4, why="secrets: 403")
    servers = per_world()
    async with httpx.AsyncClient(transport=httpx.MockTransport(receiver.answer)) as http:
        handles = Handles(load_settings(), VAULT, http, servers, LocalSignal(), sessions)
        async with sessions() as session:
            await raise_alert(session, handles, logs, Scope(tenant.org, Env.sandbox), None, failed)
    for server in servers.values():
        await server.aclose()
    assert logs.written == []
    (posted,) = receiver.heard
    body = json.loads(posted.content)
    assert posted.headers["x-pinecall-event"] == "app.failed"
    assert (body["type"], body["org"], body["env"], body["agent"]) == ("app.failed", tenant.org, "sandbox", None)
    assert body["data"] == {"app": "support", "host": "support-r4-e8033b63", "release": 4, "why": "secrets: 403"}
