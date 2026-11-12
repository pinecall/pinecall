"""The private values of one entry, sealed under the vault, keyed by log and seq."""

from sqlalchemy import BigInteger, Text
from sqlalchemy.orm import Mapped, mapped_column

from runtime.kit.db import Kept, Model, Sealed


class CallPrivate(Model):
    """What the log masked: a tool's `pii` arguments, a state field declared `pii`."""

    __tablename__ = "call_private"
    __kept__ = Kept(
        call="log",
        not_exported=(
            "the values an agent declared private, sealed under the box's vault: an export carries each entry "
            "as the log keeps it, masked"
        ),
    )

    log: Mapped[str] = mapped_column(Text, primary_key=True)
    seq: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    sealed: Mapped[str] = mapped_column(Sealed, nullable=False)
