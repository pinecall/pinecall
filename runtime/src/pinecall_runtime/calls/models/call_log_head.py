"""A log's head: its last seq, whether it is sealed, whose it is, and the seal's lease."""

from datetime import datetime

from sqlalchemy import TIMESTAMP, BigInteger, Boolean, Float, Index, Integer, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from pinecall_runtime.enums import Env, Opener
from pinecall_runtime.kit.db import Model, StringEnum


class CallLogHead(Model):
    """One row per log, locked when the log is written."""

    __tablename__ = "call_log_head"
    __table_args__ = (
        Index("call_log_head_by_agent", "agent", "started_at", postgresql_where="call IS NOT NULL"),
        Index(
            "call_log_head_by_corner",
            "org",
            "env",
            "holder",
            text("started_at DESC"),
            postgresql_where="call IS NOT NULL",
        ),
    )

    log: Mapped[str] = mapped_column(Text, primary_key=True)
    agent: Mapped[str | None] = mapped_column(Text)
    call: Mapped[str | None] = mapped_column(Text)
    seq: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    sealed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    started_at: Mapped[float | None] = mapped_column(Float)
    org: Mapped[str | None] = mapped_column(Text)
    env: Mapped[Env | None] = mapped_column(StringEnum(Env))
    holder: Mapped[str | None] = mapped_column(Text)
    config_version: Mapped[int | None] = mapped_column(Integer)
    lexicon_version: Mapped[int | None] = mapped_column(Integer)
    # How many entries the log took from its worker's batches, and the seq of the last.
    written: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    written_seq: Mapped[int | None] = mapped_column(BigInteger)
    # The seal's lease: who holds the right to seal, and until when.
    sealing_until: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    sealing_by: Mapped[str | None] = mapped_column(Text)
    opened_by: Mapped[Opener | None] = mapped_column(StringEnum(Opener))
