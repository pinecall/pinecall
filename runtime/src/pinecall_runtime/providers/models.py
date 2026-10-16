"""The providers tables: provider_keys."""

from datetime import datetime

from sqlalchemy import TIMESTAMP, ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column

from pinecall_runtime.kit.db import Model, utc_now


class ProviderKey(Model):
    """One row per org and vendor."""

    __tablename__ = "provider_keys"

    org: Mapped[str] = mapped_column(ForeignKey("orgs.id", ondelete="CASCADE"), primary_key=True)
    vendor: Mapped[str] = mapped_column(Text, primary_key=True)
    ciphertext: Mapped[str] = mapped_column(Text, nullable=False)
    set_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False, default=utc_now)
