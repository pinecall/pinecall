"""A log's head: its last seq, whether it is sealed, whose it is, and the seal's lease."""

from datetime import datetime
from enum import StrEnum

from sqlalchemy import TIMESTAMP, BigInteger, Boolean, Float, Index, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column

from runtime.enums import Env
from runtime.kit.db import Kept, Model, StringEnum, descending


class Opener(StrEnum):
    """Who opened a call's log."""

    fleet = "fleet"
    app = "app"
    gateway = "gateway"


# The row names its org with no key to it (a head is made before its call names an org: the seal's
# lease, a seal), so nothing cascades: an org erased has its logs deleted by the verb named here.
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
            descending("started_at"),
            postgresql_where="call IS NOT NULL",
        ),
    )
    __kept__ = Kept(
        call="log",
        agent="agent",
        exported=("call", "agent", "holder", "started_at", "sealed"),
        exported_by="calls.service.exporting.export_calls",
        erased_by="calls.service.erasing.erase_logs",
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
    # The test run the call is one of (a golden's), for a list to say so; none for anybody's call.
    run: Mapped[str | None] = mapped_column(Text)
    # The versions of the agent's settings and of its lexicon the call was built on.
    config_version: Mapped[int | None] = mapped_column(Integer)
    lexicon_version: Mapped[int | None] = mapped_column(Integer)
    # How many entries the log took from its worker's batches, and the seq of the last.
    written: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    written_seq: Mapped[int | None] = mapped_column(BigInteger)
    # The seal's lease: who holds the right to seal, and until when.
    sealing_until: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    sealing_by: Mapped[str | None] = mapped_column(Text)
    opened_by: Mapped[Opener | None] = mapped_column(StringEnum(Opener))
