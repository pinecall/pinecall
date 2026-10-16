"""When a reader last read a contact's thread with an agent."""

from sqlalchemy import Float, Text
from sqlalchemy.orm import Mapped, mapped_column

from pinecall_runtime.enums import Env
from pinecall_runtime.kit.db import Model, StringEnum


class ThreadRead(Model):
    """What tells the inbox which threads are unread, per reader."""

    __tablename__ = "thread_reads"

    org: Mapped[str] = mapped_column(Text, primary_key=True)
    env: Mapped[Env] = mapped_column(StringEnum(Env), primary_key=True)
    holder: Mapped[str] = mapped_column(Text, primary_key=True)
    agent: Mapped[str] = mapped_column(Text, primary_key=True)
    reader: Mapped[str] = mapped_column(Text, primary_key=True)
    contact: Mapped[str] = mapped_column(Text, primary_key=True)
    read_at: Mapped[float] = mapped_column(Float, nullable=False)
