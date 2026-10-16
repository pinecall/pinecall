"""The private values of one entry, sealed under the vault, keyed by log and seq."""

from sqlalchemy import BigInteger, Text
from sqlalchemy.orm import Mapped, mapped_column

from pinecall_runtime.kit.db import Model


class CallPrivate(Model):
    """What the log masked: a tool's `pii` arguments, a state field declared `pii`."""

    __tablename__ = "call_private"

    log: Mapped[str] = mapped_column(Text, primary_key=True)
    seq: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    sealed: Mapped[str] = mapped_column(Text, nullable=False)
