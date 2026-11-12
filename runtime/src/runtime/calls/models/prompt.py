"""A block of prompt an org's calls were told, kept once under its hash."""

from datetime import datetime

from sqlalchemy import TIMESTAMP, ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column

from runtime.kit.db import Kept, Model, utc_now


# Until 2026-11 the table was agents', who never read it: a block is named by a call's log
# (`prompt.changed` carries its hash), and read back with that log (agents-8).
class Prompt(Model):
    """The words behind the hash a `prompt.changed` entry names, so a call's prompt reads back whole."""

    __tablename__ = "prompts"
    __kept__ = Kept(exported=("hash", "text", "first_used_at"))

    org: Mapped[str] = mapped_column(ForeignKey("orgs.id", ondelete="CASCADE"), primary_key=True)
    hash: Mapped[str] = mapped_column(Text, primary_key=True)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    first_used_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False, default=utc_now)
