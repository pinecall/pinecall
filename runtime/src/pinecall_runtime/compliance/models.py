"""The compliance tables: org_policy, org_telemetry, reads, recording_keys."""

from datetime import datetime

from sqlalchemy import TIMESTAMP, BigInteger, Boolean, ForeignKey, Identity, Index, Integer, SmallInteger, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from pinecall_runtime.enums import Env, ReadKind
from pinecall_runtime.kit.db import Model, StringEnum, utc_now


class OrgPolicy(Model):
    """How long calls are kept, when and how often a number may be rung, what a call says first."""

    __tablename__ = "org_policy"

    org: Mapped[str] = mapped_column(ForeignKey("orgs.id", ondelete="CASCADE"), primary_key=True)
    # NULL keeps calls until the org erases them.
    retention_days: Mapped[int | None] = mapped_column(Integer)
    set_by: Mapped[str] = mapped_column(Text, nullable=False)
    set_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False, default=utc_now)
    calling_from: Mapped[int | None] = mapped_column(SmallInteger)
    calling_until: Mapped[int | None] = mapped_column(SmallInteger)
    per_number_day: Mapped[int | None] = mapped_column(Integer)
    consent_everywhere: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # NULL is the platform's sentence, '' is none.
    disclosure: Mapped[str | None] = mapped_column(Text)
    recording_notice: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class OrgTelemetry(Model):
    """The endpoint in clear, the headers sealed, and whether a span may carry PII."""

    __tablename__ = "org_telemetry"

    org: Mapped[str] = mapped_column(Text, primary_key=True)
    endpoint: Mapped[str] = mapped_column(Text, nullable=False)
    ciphertext: Mapped[str | None] = mapped_column(Text)
    pii: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    set_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False, default=utc_now)


class Read(Model):
    """One row per reader, subject and kind an hour; names the subject, never what it said."""

    __tablename__ = "reads"
    __table_args__ = (
        Index("reads_by_org", "org", text("at DESC")),
        Index("reads_by_subject", "org", "subject", text("at DESC")),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    org: Mapped[str] = mapped_column(ForeignKey("orgs.id", ondelete="CASCADE"), nullable=False)
    env: Mapped[Env | None] = mapped_column(StringEnum(Env))
    subject: Mapped[str] = mapped_column(Text, nullable=False)
    what: Mapped[ReadKind] = mapped_column(StringEnum(ReadKind), nullable=False)
    reader: Mapped[str] = mapped_column(Text, nullable=False)
    at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False, default=utc_now)


class RecordingKey(Model):
    """What opens the call's audio; a backup that outlives the erasure no longer opens."""

    __tablename__ = "recording_keys"

    call: Mapped[str] = mapped_column(Text, primary_key=True)
    org: Mapped[str] = mapped_column(Text, nullable=False)
    sealed: Mapped[str] = mapped_column(Text, nullable=False)
    made_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False, default=utc_now)
