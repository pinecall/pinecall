"""The retention table: erasures, the trail of what was erased and who asked."""

from datetime import datetime

from sqlalchemy import TIMESTAMP, BigInteger, Identity, Index, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column

from runtime.enums import Env, ErasureKind
from runtime.kit.db import Kept, Model, StringEnum, descending, utc_now


class Erasure(Model):
    """A call's, a contact's, an agent's or an org's rows and recordings, counted."""

    __tablename__ = "erasures"
    __table_args__ = (Index("erasures_by_org", "org", descending("at")),)
    __kept__ = Kept(
        not_exported="the box's trail of what was erased and who asked: the org reads it at /v1/org/erasures",
        outlives=(
            "the trail is what is left to say an erasure happened: it names its org by id, with no key to it, "
            "counts what went, and names nobody"
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    org: Mapped[str] = mapped_column(Text, nullable=False)
    env: Mapped[Env | None] = mapped_column(StringEnum(Env))
    what: Mapped[ErasureKind] = mapped_column(StringEnum(ErasureKind), nullable=False)
    subject: Mapped[str] = mapped_column(Text, nullable=False)
    asked_by: Mapped[str] = mapped_column(Text, nullable=False)
    calls: Mapped[int] = mapped_column(Integer, nullable=False)
    entries: Mapped[int] = mapped_column(BigInteger, nullable=False)
    memories: Mapped[int] = mapped_column(Integer, nullable=False)
    recordings: Mapped[int] = mapped_column(Integer, nullable=False)
    at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False, default=utc_now)
