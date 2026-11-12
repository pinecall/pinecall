"""The whatsapp table: whatsapp_seen, and what claiming a message answers a delivery."""

from datetime import datetime
from enum import StrEnum

from sqlalchemy import TIMESTAMP, ForeignKey, Index, Text
from sqlalchemy.orm import Mapped, mapped_column

from runtime.kit.db import Kept, Model


# `new`: this delivery claimed it and reads it; `seen`: another read it; `reading`: another
# delivery is reading it now, and Meta must be told to come back.
class Claim(StrEnum):
    """What claiming a message answers the delivery that asked."""

    new = "new"
    seen = "seen"
    reading = "reading"


class WhatsappSeen(Model):
    """Claimed before it is read; `read_at` once queued or kept. Forgotten after Meta's 7 days."""

    __tablename__ = "whatsapp_seen"
    __table_args__ = (Index("whatsapp_seen_claimed_at", "claimed_at"),)
    __kept__ = Kept(
        not_exported=(
            "the ids of the messages Meta delivered, kept seven days so a delivery made again is dropped: "
            "what a message said is in its call's log"
        )
    )

    org: Mapped[str] = mapped_column(ForeignKey("orgs.id", ondelete="CASCADE"), primary_key=True)
    message_id: Mapped[str] = mapped_column(Text, primary_key=True)
    claimed_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    read_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
