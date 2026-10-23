"""The alerts tables: monitors, org_webhooks, and alerts, every one an org was raised."""

from datetime import date, datetime
from typing import Any

from sqlalchemy import TIMESTAMP, Boolean, Date, Float, ForeignKey, Index, Integer, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from pinecall_runtime.enums import Env, MonitorMetric
from pinecall_runtime.kit.db import Model, StringEnum, utc_now


class Monitor(Model):
    """Fired at most once a day, on the agent's log and the org's webhook."""

    __tablename__ = "monitors"
    __table_args__ = (Index("monitors_by_scope", "org", "env"),)

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


class OrgWebhook(Model):
    """One row per org."""

    __tablename__ = "org_webhooks"

    org: Mapped[str] = mapped_column(Text, primary_key=True)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    ciphertext: Mapped[str | None] = mapped_column(Text)
    set_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False, default=utc_now)


class Alert(Model):
    """One alert as it was raised: kept whatever else it reached, and whether it was mailed."""

    __tablename__ = "alerts"
    __table_args__ = (Index("alerts_by_org", "org", "env", "at"),)

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    org: Mapped[str] = mapped_column(ForeignKey("orgs.id", ondelete="CASCADE"), nullable=False)
    env: Mapped[Env] = mapped_column(StringEnum(Env), nullable=False)
    # NULL for an alert that is no one agent's: a hosted app that went down.
    agent: Mapped[str | None] = mapped_column(Text)
    kind: Mapped[str] = mapped_column(Text, nullable=False)
    # What the alert is about within its kind (the monitor, the app, the quota): mail is once an hour each.
    subject: Mapped[str] = mapped_column(Text, nullable=False, default="")
    data: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    mailed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False, default=utc_now)
