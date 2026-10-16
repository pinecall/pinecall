"""The monitors and the org's webhook row; and the org's spend by day, read off the calls' facts."""

from collections.abc import Sequence
from datetime import date

from sqlalchemy import delete, func, update
from sqlalchemy.dialects.postgresql import insert as upsert

from pinecall_runtime.alerts.models import Monitor, OrgWebhook
from pinecall_runtime.enums import Env
from pinecall_runtime.kit.repository import Repository


class MonitorRepository(Repository[Monitor]):
    """The org's monitors, per env; each remembers the last day it fired."""

    model = Monitor

    async def of_env(self, org: str, env: Env) -> Sequence[Monitor]:
        """Every monitor of the env, oldest first."""
        statement = (
            self.statement().where(Monitor.org == org, Monitor.env == env).order_by(Monitor.created_at, Monitor.id)
        )
        return await self.all(statement)

    async def drop(self, org: str, env: Env, monitor_id: str) -> bool:
        """Forget a monitor of the env; whether it was there."""
        statement = delete(Monitor).where(Monitor.org == org, Monitor.env == env, Monitor.id == monitor_id)
        return await self.changed(statement) > 0

    # The update is the once-a-day guard: two seals of the same day race to it and one wins.
    async def mark_fired(self, monitor_id: str, day: date, value: float) -> bool:
        """Mark the monitor as fired today with the value; False when it already had."""
        statement = (
            update(Monitor)
            .where(Monitor.id == monitor_id, (Monitor.fired_on.is_(None)) | (Monitor.fired_on < day))
            .values(fired_on=day, fired_value=value)
        )
        return await self.changed(statement) > 0


class WebhookRepository(Repository[OrgWebhook]):
    """One row per org: where its alerts are posted."""

    model = OrgWebhook

    async def get(self, org: str) -> OrgWebhook | None:
        """The org's webhook row, or None when its alerts go nowhere."""
        return await self.one_or_none(self.statement().where(OrgWebhook.org == org))

    async def put(self, org: str, *, url: str, ciphertext: str | None) -> None:
        """Keep where the org's alerts go, replacing what it had."""
        statement = upsert(OrgWebhook).values(org=org, url=url, ciphertext=ciphertext)
        replaced = {"url": statement.excluded.url, "ciphertext": statement.excluded.ciphertext, "set_at": func.now()}
        await self.session.execute(statement.on_conflict_do_update(index_elements=["org"], set_=replaced))

    async def drop(self, org: str) -> bool:
        """Forget where the org's alerts went; whether they went anywhere."""
        return await self.changed(delete(OrgWebhook).where(OrgWebhook.org == org)) > 0
