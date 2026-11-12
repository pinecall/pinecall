"""Every statement on the alerts tables: the monitors, the org's webhook row, and the alerts kept."""

from collections.abc import Sequence
from datetime import date, datetime

from sqlalchemy import delete, func, literal, select, update

from runtime.alerts.models import Alert, AlertKind, Monitor, OrgWebhook
from runtime.enums import Env
from runtime.kit.repository import Repository
from runtime.kit.time import now


class MonitorRepository(Repository[Monitor]):
    """The org's monitors, per env; each remembers the last day it fired."""

    model = Monitor

    async def list_of_env(self, org: str, env: Env) -> Sequence[Monitor]:
        """Every monitor of the env, oldest first."""
        statement = (
            self.statement().where(Monitor.org == org, Monitor.env == env).order_by(Monitor.created_at, Monitor.id)
        )
        return await self.all(statement)

    async def find(self, org: str, env: Env, monitor_id: str) -> Monitor | None:
        """The env's monitor by its id, or None."""
        return await self.one_or_none(
            self.statement().where(Monitor.org == org, Monitor.env == env, Monitor.id == monitor_id)
        )

    # The update is the once-a-day guard: two seals of the same day race to it and one wins.
    async def mark_fired(self, monitor_id: str, day: date, value: float) -> bool:
        """Mark the monitor as fired today with the value; False when it already had."""
        statement = (
            update(Monitor)
            .where(Monitor.id == monitor_id, (Monitor.fired_on.is_(None)) | (Monitor.fired_on < day))
            .values(fired_on=day, fired_value=value)
        )
        return await self.change(statement) > 0


class WebhookRepository(Repository[OrgWebhook]):
    """One row per org: where its alerts are posted."""

    model = OrgWebhook

    async def find(self, org: str) -> OrgWebhook | None:
        """The org's webhook row, or None when its alerts go nowhere."""
        return await self.one_or_none(self.statement().where(OrgWebhook.org == org))

    async def put(self, org: str, *, url: str, ciphertext: str | None) -> OrgWebhook:
        """Keep where the org's alerts go, replacing what it had."""
        return await self.upsert({"org": org, "url": url, "ciphertext": ciphertext, "set_at": now()}, key=["org"])

    async def delete_of_org(self, org: str) -> bool:
        """Forget where the org's alerts went; whether they went anywhere."""
        return await self.change(delete(OrgWebhook).where(OrgWebhook.org == org)) > 0


class AlertRepository(Repository[Alert]):
    """Every alert kept: an org's newest first, the box's across orgs, the ones to post, and the old ones forgotten."""

    model = Alert

    async def list_newest(
        self, org: str | None, env: Env | None, *, limit: int, before: datetime | None
    ) -> Sequence[Alert]:
        """The newest alerts, of one org and env or of every one; those before a moment, when given."""
        statement = self.statement()
        if org is not None:
            statement = statement.where(Alert.org == org)
        if env is not None:
            statement = statement.where(Alert.env == env)
        if before is not None:
            statement = statement.where(Alert.at < before)
        return await self.all(statement.order_by(Alert.at.desc(), Alert.id.desc()).limit(limit))

    # In either env: what is said once is said once to the org (its spend is one, whichever env's call
    # sealed), and a monitor's id or an org's names its env by itself.
    async def has_said_since(self, org: str, kind: AlertKind, subject: str, since: datetime) -> bool:
        """Whether the org was raised an alert of this kind and subject since then, mailed or not."""
        statement = self.statement().where(
            Alert.org == org, Alert.kind == kind, Alert.subject == subject, Alert.at >= since
        )
        return await self.exists(statement)

    async def has_mailed_since(self, org: str, env: Env, kind: AlertKind, subject: str, since: datetime) -> bool:
        """Whether an alert of this kind and subject was mailed in the env since then."""
        statement = self.statement().where(
            Alert.org == org,
            Alert.env == env,
            Alert.kind == kind,
            Alert.subject == subject,
            Alert.mailed,
            Alert.at >= since,
        )
        return await self.exists(statement)

    async def list_failed_calls(self, org: str) -> set[str]:
        """The calls a vendor failed for the org, in either env, as their alerts named them."""
        statement = select(Alert.data["call"].astext).where(Alert.org == org, Alert.kind == AlertKind.vendor_failed)
        return {str(call) for call in (await self.session.execute(statement)).scalars() if call}

    # A transaction-scoped advisory lock, released at commit or rollback. Two transactions saying the same
    # thing to the same org at once would both find it unsaid and both say it: the first to take the lock
    # says it, the second is refused the lock, and whoever comes later finds the alert kept.
    #
    # The release before 2026-11 claims a quiet org as `org.quiet:<org>`, the subject alone, and sweeps the
    # newborns beside this one for the hour a rollout takes: an alert whose subject is its org keeps that
    # key, so the two never point at one org together. It goes when that release does.
    async def claim(self, org: str, kind: AlertKind, subject: str) -> bool:
        """Take the transaction's lock on this kind and subject of the org; False when another transaction holds it."""
        key = f"{kind.value}:{subject}" if subject == org else f"{kind.value}:{org}:{subject}"
        taken = await self.session.execute(select(func.pg_try_advisory_xact_lock(func.hashtext(literal(key)))))
        return bool(taken.scalar_one())

    # The rows are locked as they are read and another gateway's are skipped, so of two gateways passing
    # at once each takes its own; a row is marked in the transaction that took it.
    async def take_unposted(self, limit: int, at: datetime) -> Sequence[Alert]:
        """The oldest alerts nobody posted, each marked as taken at the moment; at most `limit`."""
        statement = (
            self.statement()
            .where(Alert.posted_at.is_(None))
            .order_by(Alert.at, Alert.id)
            .limit(limit)
            .with_for_update(skip_locked=True)
        )
        rows = await self.all(statement)
        for row in rows:
            row.posted_at = at
        await self.session.flush()
        return rows

    async def delete_before(self, cut: datetime) -> int:
        """Forget every alert raised before the cut; how many. Run box-wide by the caller."""
        return await self.change(delete(Alert).where(Alert.at < cut))
