"""The hosting tables: hosted_apps, hosted_releases, hosted_usage, org_secrets."""

from datetime import date, datetime

from sqlalchemy import (
    TIMESTAMP,
    Date,
    Float,
    ForeignKey,
    ForeignKeyConstraint,
    Integer,
    LargeBinary,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column

from pinecall_runtime.enums import Env
from pinecall_runtime.kit.db import Model, StringEnum, utc_now


class HostedApp(Model):
    """One app per org, env and name, with the server's token its process runs on, sealed."""

    __tablename__ = "hosted_apps"

    org: Mapped[str] = mapped_column(ForeignKey("orgs.id", ondelete="CASCADE"), primary_key=True)
    env: Mapped[Env] = mapped_column(StringEnum(Env), primary_key=True)
    name: Mapped[str] = mapped_column(Text, primary_key=True)
    key_fingerprint: Mapped[str] = mapped_column(Text, nullable=False)
    sealed_key: Mapped[str] = mapped_column(Text, nullable=False)
    # `code` the runner starts from its sources; `studio` the gateway holds, its key columns empty.
    kind: Mapped[str] = mapped_column(Text, nullable=False, server_default="code", default="code")
    created_by: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False, default=utc_now)
    # What the runner last said: the release it serves and under which host, or what failed.
    live_release: Mapped[int | None] = mapped_column(Integer)
    live_host: Mapped[str | None] = mapped_column(Text)
    failed_host: Mapped[str | None] = mapped_column(Text)
    failed_why: Mapped[str] = mapped_column(Text, nullable=False, default="")
    reported_by: Mapped[str] = mapped_column(Text, nullable=False, default="")
    reported_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    stopped_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    stopped_by: Mapped[str] = mapped_column(Text, nullable=False, default="")
    logs_asked_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    logs: Mapped[str] = mapped_column(Text, nullable=False, default="")
    logs_host: Mapped[str | None] = mapped_column(Text)
    logs_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    metered_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))

    @property
    def is_running(self) -> bool:
        """Whether the runner is told to run it."""
        return self.stopped_at is None


class HostedRelease(Model):
    """An upload: numbered from 1, never edited."""

    __tablename__ = "hosted_releases"
    __table_args__ = (
        ForeignKeyConstraint(
            ["org", "env", "name"],
            ["hosted_apps.org", "hosted_apps.env", "hosted_apps.name"],
            ondelete="CASCADE",
        ),
    )

    org: Mapped[str] = mapped_column(Text, primary_key=True)
    env: Mapped[Env] = mapped_column(StringEnum(Env), primary_key=True)
    name: Mapped[str] = mapped_column(Text, primary_key=True)
    release: Mapped[int] = mapped_column(Integer, primary_key=True)
    source: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    sha256: Mapped[str] = mapped_column(Text, nullable=False)
    bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    author: Mapped[str] = mapped_column(Text, nullable=False, default="")
    note: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False, default=utc_now)


class HostedUsage(Model):
    """The seconds an app served each UTC day: what the org is billed for, so it outlives the app."""

    __tablename__ = "hosted_usage"

    org: Mapped[str] = mapped_column(ForeignKey("orgs.id", ondelete="CASCADE"), primary_key=True)
    env: Mapped[Env] = mapped_column(StringEnum(Env), primary_key=True)
    name: Mapped[str] = mapped_column(Text, primary_key=True)
    day: Mapped[date] = mapped_column(Date, primary_key=True)
    seconds: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)


class OrgSecret(Model):
    """Name and sealed value."""

    __tablename__ = "org_secrets"

    org: Mapped[str] = mapped_column(ForeignKey("orgs.id", ondelete="CASCADE"), primary_key=True)
    env: Mapped[Env] = mapped_column(StringEnum(Env), primary_key=True)
    name: Mapped[str] = mapped_column(Text, primary_key=True)
    sealed: Mapped[str] = mapped_column(Text, nullable=False)
    set_by: Mapped[str] = mapped_column(Text, nullable=False, default="")
    set_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False, default=utc_now)
