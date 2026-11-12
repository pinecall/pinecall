"""The fleet tables: offers."""

from sqlalchemy import Float, Index, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column

from runtime.kit.db import Kept, Model


# The room is named by its call's id, so the row is found by the call; it never outlives two minutes.
class Offer(Model):
    """Kept from the caller's arrival until a worker opens the call; offered again when nobody did."""

    __tablename__ = "offers"
    __table_args__ = (Index("offers_due", "offered_at"), Index("offers_by_age", "seen_at"))
    __kept__ = Kept(
        call="room",
        not_exported="a room waiting for a worker, let go within two minutes: nothing an org wrote",
    )

    room: Mapped[str] = mapped_column(Text, primary_key=True)
    fleet: Mapped[str] = mapped_column(Text, nullable=False)
    # The call's dispatch, as the SIP rule or the visitor's token carried it into the room.
    dispatch: Mapped[str] = mapped_column(Text, nullable=False)
    seen_at: Mapped[float] = mapped_column(Float, nullable=False)
    worker: Mapped[str | None] = mapped_column(Text)
    offers: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    offered_at: Mapped[float | None] = mapped_column(Float)
