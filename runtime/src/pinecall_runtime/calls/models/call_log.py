"""One entry of a call's log, or of an agent's own log; append-only, partitioned by UTC day."""

from typing import Any

from sqlalchemy import BigInteger, Boolean, Computed, Float, Identity, Index, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from pinecall_runtime.kit.db import Model

# An agent's own log is named "@<agent>", a name the CHECK on call_log keeps from any call id.
AGENT_LOG_PREFIX = "@"


class CallLog(Model):
    """A line of the log: its seq within the log, its stamp, its type and data."""

    __tablename__ = "call_log"
    __table_args__ = (
        Index("call_log_metered_by_day", "type", "position"),
        {"postgresql_partition_by": "RANGE (ts)"},
    )

    call: Mapped[str | None] = mapped_column(Text)
    seq: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    # The runtime's clock when it saw the event, never the database's; part of the key.
    ts: Mapped[float] = mapped_column(Float, primary_key=True)
    agent: Mapped[str] = mapped_column(Text, nullable=False)
    type: Mapped[str] = mapped_column(Text, nullable=False)
    ephemeral: Mapped[bool] = mapped_column(Boolean, nullable=False)
    data: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    # The call's id, or "@agent" for the agent's own log.
    log: Mapped[str] = mapped_column(Text, Computed("COALESCE(call, '@' || agent)", persisted=True), primary_key=True)
    # The store's row order across every log; the metered feed resumes from it.
    position: Mapped[int] = mapped_column(BigInteger, Identity(always=True), nullable=False)


def log_name(call: str | None, agent: str) -> str:
    """The name a log goes by: the call id, or the agent's with the prefix."""
    return f"{AGENT_LOG_PREFIX}{agent}" if call is None else call
