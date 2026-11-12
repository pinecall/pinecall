"""What a call is, kept when it opens: its context, and the hash of the declaration it runs on."""

from datetime import datetime
from typing import Any

from sqlalchemy import TIMESTAMP, ForeignKey, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from runtime.kit.db import Kept, Model, utc_now


class CallOpening(Model):
    """The first opening stands: a reopen says it again and changes nothing."""

    __tablename__ = "call_openings"
    __kept__ = Kept(
        call="call",
        not_exported=(
            "what the box keeps to serve the call again: an export carries the call's entries and its facts, "
            "which say everything the opening does"
        ),
    )

    call: Mapped[str] = mapped_column(Text, primary_key=True)
    org: Mapped[str] = mapped_column(ForeignKey("orgs.id", ondelete="CASCADE"), nullable=False)
    context: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    config_hash: Mapped[str] = mapped_column(Text, nullable=False)
    opened_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False, default=utc_now)
