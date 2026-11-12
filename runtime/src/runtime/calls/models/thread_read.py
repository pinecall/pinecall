"""When a reader last read a contact's thread with an agent."""

from sqlalchemy import Float, Text
from sqlalchemy.orm import Mapped, mapped_column

from runtime.enums import Env
from runtime.kit.db import Kept, Model, StringEnum


# The row names its org with no key to it, so nothing cascades: an org erased has its readers'
# cursors deleted by the verb named here.
class ThreadRead(Model):
    """What tells the inbox which threads are unread, per reader."""

    __tablename__ = "thread_reads"
    __kept__ = Kept(
        agent="agent",
        contact="contact",
        not_exported="when a member last opened a thread: the console's own cursor, nothing the org wrote",
        erased_by="calls.service.inbox.delete_reads",
    )

    org: Mapped[str] = mapped_column(Text, primary_key=True)
    env: Mapped[Env] = mapped_column(StringEnum(Env), primary_key=True)
    holder: Mapped[str] = mapped_column(Text, primary_key=True)
    agent: Mapped[str] = mapped_column(Text, primary_key=True)
    reader: Mapped[str] = mapped_column(Text, primary_key=True)
    contact: Mapped[str] = mapped_column(Text, primary_key=True)
    read_at: Mapped[float] = mapped_column(Float, nullable=False)
