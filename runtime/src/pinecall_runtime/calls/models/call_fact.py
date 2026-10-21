"""What is known of every call without folding its log: one row, folded as entries land."""

from typing import Any

from sqlalchemy import Boolean, Float, Index, Integer, Text, text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
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
    # What a simulated caller's own model and voice cost, on the box's keys: the call's cost is the
    # agent's side, and the caller is the harness's, kept here when the simulation ends.
    caller_cost_usd: Mapped[float] = mapped_column(Float, nullable=False, default=0.0, server_default=text("0"))
    # Who played that caller, as it ran: `vendor/model` of its lines, the voice's `vendor/model` and
    # the voice. NULL for a call nobody simulated.
    caller_llm: Mapped[str | None] = mapped_column(Text)
    caller_tts: Mapped[str | None] = mapped_column(Text)
    caller_voice: Mapped[str | None] = mapped_column(Text)
    # What a list shows of the call, as its state said at the seal (`facts.line_of`): a list reads
    # it instead of folding the log. NULL while the call is live, and for a call sealed before this
    # column existed, until `facts rebuild` writes it.
    line: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
