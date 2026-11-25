"""The fleet tables: offers, seat_turns."""

from sqlalchemy import Float, Index, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column

from runtime.kit.db import Kept, Model


# The room is named by its call's id, so the row is found by the call; it never outlives two minutes.
class Offer(Model):
    """Kept from the caller's arrival until its worker says the call itself; offered again when no worker took it."""

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
    # When a worker took the room: it accepted the room's job, its agent joined, or it opened the call,
    # whichever the gateway heard first. The row then takes its slot until that worker's next heartbeat.
    opened_at: Mapped[float | None] = mapped_column(Float)


# A caller that can wait (a simulated one) is never sent the overflow's sentence: it stands in a line
# for a seat, and the line is every gateway's and every org's. Read across orgs on purpose, so no
# row-level security: whose turn a freed seat is depends on what each org holds.
class Turn(Model):
    """A caller that waits for a seat of a fleet: in line from its first ask, holding its seat from when it took it."""

    __tablename__ = "seat_turns"
    __table_args__ = (Index("seat_turns_by_fleet", "fleet"),)
    __kept__ = Kept(
        call="room",
        not_exported="a caller's place in the line for a seat, gone with its call: nothing an org wrote",
        outlives="a place in a line names its org only to share the seats, and goes when its call ends",
    )

    room: Mapped[str] = mapped_column(Text, primary_key=True)
    fleet: Mapped[str] = mapped_column(Text, nullable=False)
    # Whose caller it is; empty for a caller no org placed.
    org: Mapped[str] = mapped_column(Text, nullable=False)
    # Its first ask, which is its place among its org's callers, and its last: one that stopped asking left the line.
    asked_at: Mapped[float] = mapped_column(Float, nullable=False)
    heard_at: Mapped[float] = mapped_column(Float, nullable=False)
    # When it took its seat: from then it counts as one its org holds, until its call ends.
    seated_at: Mapped[float | None] = mapped_column(Float)
