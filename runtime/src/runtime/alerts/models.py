"""The alerts tables: monitors, org_webhooks, and alerts, every one an org was raised; and the kinds of alert."""

from datetime import date, datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import TIMESTAMP, Boolean, Date, Float, ForeignKey, Index, Integer, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from runtime.enums import Env, MonitorMetric
from runtime.kit.db import Kept, Model, Sealed, StringEnum, utc_now


# Each under the type the agent's log writes it as, and a webhook's post carries.
class AlertKind(StrEnum):
    """The kinds of alert an org is raised."""

    monitor_fired = "monitor.fired"
    spend_unusual = "spend.unusual"
    credits_exhausted = "credits.exhausted"
    app_failed = "app.failed"
    vendor_failed = "vendor.failed"
    org_quiet = "org.quiet"


class Monitor(Model):
    """Fired at most once a day, on the agent's log and the org's webhook."""

    __tablename__ = "monitors"
    __table_args__ = (Index("monitors_by_scope", "org", "env"),)
    __kept__ = Kept(
        agent="agent",
        exported=(
            "id",
            "env",
            "agent",
            "name",
            "metric",
            "above",
            "threshold",
            "window_days",
            "created_by",
            "created_at",
        ),
    )

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    org: Mapped[str] = mapped_column(ForeignKey("orgs.id", ondelete="CASCADE"), nullable=False)
    env: Mapped[Env] = mapped_column(StringEnum(Env), nullable=False)
    # NULL watches every agent of the env.
    agent: Mapped[str | None] = mapped_column(Text)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    metric: Mapped[MonitorMetric] = mapped_column(StringEnum(MonitorMetric), nullable=False)
    above: Mapped[bool] = mapped_column(Boolean, nullable=False)
    threshold: Mapped[float] = mapped_column(Float, nullable=False)
    window_days: Mapped[int] = mapped_column(Integer, nullable=False)
    created_by: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False, default=utc_now)
    fired_on: Mapped[date | None] = mapped_column(Date)
    fired_value: Mapped[float | None] = mapped_column(Float)


# No foreign key reaches the row from its org (`org` is text): the org's erasure calls `forget_webhook`.
class OrgWebhook(Model):
    """One row per org."""

    __tablename__ = "org_webhooks"
    __kept__ = Kept(exported=("url", "set_at"), erased_by="alerts.service.webhooks.forget_webhook")

    org: Mapped[str] = mapped_column(Text, primary_key=True)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    ciphertext: Mapped[str | None] = mapped_column(Sealed)
    set_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False, default=utc_now)


class Alert(Model):
    """One alert as it was raised: kept whatever else it reached, whether it was mailed, and when it was posted."""

    __tablename__ = "alerts"
    __table_args__ = (Index("alerts_by_org", "org", "env", "at"),)
    __kept__ = Kept(
        agent="agent",
        not_exported="what the box told the org of its own calls, forgotten after ninety days: nothing the org wrote",
    )

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    org: Mapped[str] = mapped_column(ForeignKey("orgs.id", ondelete="CASCADE"), nullable=False)
    env: Mapped[Env] = mapped_column(StringEnum(Env), nullable=False)
    # NULL for an alert that is no one agent's: a hosted app that went down.
    agent: Mapped[str | None] = mapped_column(Text)
    kind: Mapped[AlertKind] = mapped_column(StringEnum(AlertKind), nullable=False)
    # What the alert is about within its kind (the monitor, the app, the quota): mail is once an hour each.
    subject: Mapped[str] = mapped_column(Text, nullable=False, default="")
    data: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    mailed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False, default=utc_now)
    # NULL while the alert waits to be posted to the webhooks; the moment a gateway took it to post.
    #
    # The column is new with this package (2026-11) and the release before it knows nothing of it: that
    # release posts an alert as it raises it, inside the caller's transaction, and inserts its row without
    # naming this column. So the column's revision gives it `DEFAULT now()` in the database (and every row
    # from before reads the moment it was added): a row that release writes is born posted, and no gateway
    # of this one posts it again. This package writes NULL by name. The default goes when that release does.
    posted_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))


# What the loop that posts asks for every few seconds, on every gateway: the alerts still waiting, and
# nothing of the ninety days already posted.
Index("alerts_unposted", Alert.at, postgresql_where=Alert.posted_at.is_(None))
