"""The platform's tables: box_settings and knocks."""

from datetime import datetime
from typing import Any

from sqlalchemy import TIMESTAMP, Float, Index, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from runtime.kit.db import Kept, Model, Sealed, utc_now


class BoxSetting(Model):
    """One named value of the box (`providers`, `admission`, `brand`…); `ciphertext` where part of it is a secret."""

    __tablename__ = "box_settings"
    __kept__ = Kept(not_exported="the box's own: no org wrote it")

    name: Mapped[str] = mapped_column(Text, primary_key=True)
    value: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    ciphertext: Mapped[str | None] = mapped_column(Sealed)
    set_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False, default=utc_now)


class Attempt(Model):
    """A name tried something at this moment (a sign-in, a voice sample); rows past the window go."""

    __tablename__ = "knocks"
    __table_args__ = (Index("knocks_by_name", "name", "at"), Index("knocks_by_age", "at"))
    __kept__ = Kept(not_exported="a count that is gone in a minute")

    # The table has no primary key: SQLAlchemy needs one to map, so both columns stand as it.
    name: Mapped[str] = mapped_column(Text, primary_key=True)
    at: Mapped[float] = mapped_column(Float, primary_key=True)
