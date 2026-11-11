"""The flows tables: app_events an app is owed, flow_runs of its flows, and flow_steps, each run's journal."""

from datetime import datetime
from typing import Any

from sqlalchemy import TIMESTAMP, BigInteger, ForeignKey, Index, Integer, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from pinecall_runtime.enums import Env
from pinecall_runtime.kit.db import Model, StringEnum, utc_now


class AppEvent(Model):
    """One event sent to an app, kept until the app's process says it heard it."""

    __tablename__ = "app_events"
    __table_args__ = (Index("app_events_owed", "org", "env", "app", "id", postgresql_where="heard_at IS NULL"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    org: Mapped[str] = mapped_column(ForeignKey("orgs.id", ondelete="CASCADE"), nullable=False)
    env: Mapped[Env] = mapped_column(StringEnum(Env), nullable=False)
    app: Mapped[str] = mapped_column(Text, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    data: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    sent_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False, default=utc_now)
    # Handed to a process until then, and to the next one that asks after it.
    leased_until: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    heard_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))


class FlowRun(Model):
    """One run of a flow: what it was started with, where it stands, and what it waits for."""

    __tablename__ = "flow_runs"
    __table_args__ = (
        Index("flow_runs_by_app", "org", "env", "app", "started_at"),
        Index("flow_runs_started_once", "org", "env", "app", "flow", "key", unique=True),
        Index(
            "flow_runs_waiting", "status", "wake_at", postgresql_where="status IN ('sleeping', 'waiting', 'calling')"
        ),
    )

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    org: Mapped[str] = mapped_column(ForeignKey("orgs.id", ondelete="CASCADE"), nullable=False)
    env: Mapped[Env] = mapped_column(StringEnum(Env), nullable=False)
    app: Mapped[str] = mapped_column(Text, nullable=False)
    flow: Mapped[str] = mapped_column(Text, nullable=False)
    # What started it, said once: the same key starts no second run.
    key: Mapped[str] = mapped_column(Text, nullable=False)
    input: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    # ready · sleeping · waiting · calling · done · failed · cancelled
    status: Mapped[str] = mapped_column(Text, nullable=False, default="ready")
    # When a sleep ends, or a wait gives up; the event a wait is for and what of its data must match; the call placed.
    wake_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    waits_for: Mapped[str | None] = mapped_column(Text)
    waits_match: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    call: Mapped[str | None] = mapped_column(Text)
    error: Mapped[str | None] = mapped_column(Text)
    leased_until: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    started_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False, default=utc_now)
    moved_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False, default=utc_now)


class FlowStep(Model):
    """One step of a run's journal: what was asked, and once it is over, what it came to."""

    __tablename__ = "flow_steps"

    run: Mapped[str] = mapped_column(ForeignKey("flow_runs.id", ondelete="CASCADE"), primary_key=True)
    seq: Mapped[int] = mapped_column(Integer, primary_key=True)
    org: Mapped[str] = mapped_column(ForeignKey("orgs.id", ondelete="CASCADE"), nullable=False)
    # sleep · call · wait · run · emit
    kind: Mapped[str] = mapped_column(Text, nullable=False)
    asked: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    # NULL while the step is not over; {"value": …} once it is: a step that came to nothing is not one still open.
    result: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False, default=utc_now)
