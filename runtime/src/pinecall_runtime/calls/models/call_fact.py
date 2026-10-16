"""What is known of every call without folding its log: one row, folded as entries land."""

from sqlalchemy import Boolean, Float, Index, Integer, Text
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column

from pinecall_runtime.kit.db import Model


class CallFact(Model):
    """The call as its lists, counts and inbox see it; every field comes from some entry."""

    __tablename__ = "call_facts"
    __table_args__ = (
        Index("call_facts_by_contact", "contact", postgresql_where="contact IS NOT NULL"),
        Index("call_facts_by_persona", "persona", postgresql_where="persona IS NOT NULL"),
    )

    call: Mapped[str] = mapped_column(Text, primary_key=True)
    channel: Mapped[str | None] = mapped_column(Text)
    direction: Mapped[str | None] = mapped_column(Text)
    from_number: Mapped[str | None] = mapped_column(Text)
    to_number: Mapped[str | None] = mapped_column(Text)
    name: Mapped[str | None] = mapped_column(Text)
    # The inbox key: the app's contact id, else the number or the visitor id.
    contact: Mapped[str | None] = mapped_column(Text)
    persona: Mapped[str | None] = mapped_column(Text)
    spoken: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    ended_at: Mapped[float | None] = mapped_column(Float)
    end_reason: Mapped[str | None] = mapped_column(Text)
    outcome: Mapped[str | None] = mapped_column(Text)
    cost_usd: Mapped[float | None] = mapped_column(Float)
    cost_llm_usd: Mapped[float | None] = mapped_column(Float)
    cost_stt_usd: Mapped[float | None] = mapped_column(Float)
    cost_tts_usd: Mapped[float | None] = mapped_column(Float)
    cost_phone_usd: Mapped[float | None] = mapped_column(Float)
    cost_platform_usd: Mapped[float | None] = mapped_column(Float)
    judged: Mapped[int | None] = mapped_column(Integer)
    held: Mapped[int | None] = mapped_column(Integer)
    passed: Mapped[bool | None] = mapped_column(Boolean)
    reason: Mapped[str | None] = mapped_column(Text)
    escalated: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    promised: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    e2e: Mapped[list[float]] = mapped_column(ARRAY(Float(asdecimal=False)), nullable=False, default=list[float])
    heard_at: Mapped[list[float]] = mapped_column(ARRAY(Float(asdecimal=False)), nullable=False, default=list[float])
    last_text: Mapped[str | None] = mapped_column(Text)
    last_at: Mapped[float | None] = mapped_column(Float)
    last_in: Mapped[bool | None] = mapped_column(Boolean)
    # The vendors the call ran on the box's own key: the operator's to bill.
    lent: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False, default=list)
