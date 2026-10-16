"""The retention tables: call_records, erasures."""

from datetime import datetime

from sqlalchemy import TIMESTAMP, BigInteger, Float, Identity, Index, Integer, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from pinecall_runtime.enums import Env, ErasureKind
from pinecall_runtime.kit.db import Model, StringEnum, utc_now


class CallRecord(Model):
    """No name, no words, no outcome: what a carrier's traceback asks. Outlives its org."""

    __tablename__ = "call_records"
    __table_args__ = (
        Index("call_records_from", "from_number", "started_at"),
        Index("call_records_to", "to_number", "started_at"),
    )

    call: Mapped[str] = mapped_column(Text, primary_key=True)
    org: Mapped[str | None] = mapped_column(Text)
    env: Mapped[Env | None] = mapped_column(StringEnum(Env))
    direction: Mapped[str | None] = mapped_column(Text)
    from_number: Mapped[str | None] = mapped_column(Text)
    to_number: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[float | None] = mapped_column(Float)
    ended_at: Mapped[float | None] = mapped_column(Float)
    end_reason: Mapped[str | None] = mapped_column(Text)
    erased_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False, default=utc_now)


class Erasure(Model):
    """A call's, a contact's, an agent's or an org's rows and recordings, counted."""

    __tablename__ = "erasures"
    __table_args__ = (Index("erasures_by_org", "org", text("at DESC")),)

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    org: Mapped[str] = mapped_column(Text, nullable=False)
    env: Mapped[Env | None] = mapped_column(StringEnum(Env))
    what: Mapped[ErasureKind] = mapped_column(StringEnum(ErasureKind), nullable=False)
    subject: Mapped[str] = mapped_column(Text, nullable=False)
    asked_by: Mapped[str] = mapped_column(Text, nullable=False)
    calls: Mapped[int] = mapped_column(Integer, nullable=False)
    entries: Mapped[int] = mapped_column(BigInteger, nullable=False)
    memories: Mapped[int] = mapped_column(Integer, nullable=False)
    recordings: Mapped[int] = mapped_column(Integer, nullable=False)
    at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False, default=utc_now)
