"""What a carrier's traceback keeps of a phone call once its log is erased: its numbers, its times, how it ended."""

from datetime import datetime

from sqlalchemy import TIMESTAMP, Float, Index, Text
from sqlalchemy.orm import Mapped, mapped_column

from runtime.enums import Env
from runtime.kit.db import Kept, Model, StringEnum, utc_now


# Written by the erasure that takes the call's log, off its facts, before they go; forgotten two years on.
class CallRecord(Model):
    """No name, no words, no outcome: what a carrier's traceback asks. Outlives its call and its org."""

    __tablename__ = "call_records"
    __table_args__ = (
        Index("call_records_from", "from_number", "started_at"),
        Index("call_records_to", "to_number", "started_at"),
    )
    __kept__ = Kept(
        outlives=(
            "the numbers and the times of an erased phone call, kept two years for a carrier's traceback: "
            "it names numbers and moments, never who spoke or what was said"
        ),
        not_exported="the box's record for a carrier's traceback, written when the org's own data was erased",
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
