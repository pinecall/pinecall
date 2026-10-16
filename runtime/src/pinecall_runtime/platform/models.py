"""The platform tables: box_settings."""

from datetime import datetime
from typing import Any

from sqlalchemy import TIMESTAMP, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from pinecall_runtime.kit.db import Model, utc_now


class BoxSetting(Model):
    """`providers`, `admission`, `fleets`, `brand`…; `ciphertext` where the value is a secret."""

    __tablename__ = "box_settings"

    name: Mapped[str] = mapped_column(Text, primary_key=True)
    value: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    ciphertext: Mapped[str | None] = mapped_column(Text)
    set_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False, default=utc_now)
