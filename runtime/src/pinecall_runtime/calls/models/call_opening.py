"""What a call is, kept when it opens: its context, and the hash of the config it runs on."""

from datetime import datetime
from typing import Any

from sqlalchemy import TIMESTAMP, ForeignKey, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from pinecall_runtime.kit.db import Model, utc_now


class CallOpening(Model):
    """The first opening stands: a reopen says it again and changes nothing."""

    __tablename__ = "call_openings"

    call: Mapped[str] = mapped_column(Text, primary_key=True)
    org: Mapped[str] = mapped_column(ForeignKey("orgs.id", ondelete="CASCADE"), nullable=False)
    context: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    config_hash: Mapped[str] = mapped_column(Text, nullable=False)
    opened_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False, default=utc_now)
