"""The channels tables: routes, whatsapp_seen."""

from datetime import datetime

from sqlalchemy import TIMESTAMP, Boolean, ForeignKey, ForeignKeyConstraint, Index, Text
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column

from pinecall_runtime.enums import Channel, Env, RouteOrigin
from pinecall_runtime.kit.db import Model, StringEnum, utc_now


class Route(Model):
    """A number's row: its agent, channel, env, how it was written and whether it was approved."""

    __tablename__ = "routes"
    __table_args__ = (
        ForeignKeyConstraint(["org", "account"], ["carriers.org", "carriers.account"], ondelete="SET NULL (account)"),
        # One org holds a number.
        Index("routes_number_held_once", "number", unique=True),
    )

    org: Mapped[str] = mapped_column(Text, primary_key=True)
    number: Mapped[str] = mapped_column(Text, primary_key=True)
    agent: Mapped[str] = mapped_column(Text, nullable=False)
    channel: Mapped[Channel] = mapped_column(StringEnum(Channel), nullable=False)
    added_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False, default=utc_now)
    env: Mapped[Env] = mapped_column(StringEnum(Env), nullable=False)
    # Bought on the box's carrier account: counts against the `numbers` quota.
    managed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # The org's carrier account the number lives in, or NULL.
    account: Mapped[str | None] = mapped_column(Text)
    # A hooked number's own networks, which the operator approves.
    networks: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False, default=list)
    origin: Mapped[RouteOrigin] = mapped_column(StringEnum(RouteOrigin), nullable=False, default=RouteOrigin.typed)
    # The catalog carrier a number with no account comes through.
    via: Mapped[str | None] = mapped_column(Text)
    last_call_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    approved_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), default=utc_now)
    approved_by: Mapped[str | None] = mapped_column(Text)

    @property
    def approved(self) -> bool:
        """Whether a call to the number may open."""
        return self.approved_at is not None


class WhatsappSeen(Model):
    """Claimed before it is read; `read_at` once queued or kept. Forgotten after Meta's 7 days."""

    __tablename__ = "whatsapp_seen"
    __table_args__ = (Index("whatsapp_seen_claimed_at", "claimed_at"),)

    org: Mapped[str] = mapped_column(ForeignKey("orgs.id", ondelete="CASCADE"), primary_key=True)
    message_id: Mapped[str] = mapped_column(Text, primary_key=True)
    claimed_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    read_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
