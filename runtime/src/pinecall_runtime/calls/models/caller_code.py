"""The four-digit codes a caller keys to tie their call to a browser page, and how many each call tried."""

from sqlalchemy import Float, Index, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column

from pinecall_runtime.enums import CodeLog, Env
from pinecall_runtime.kit.db import Model, StringEnum


class CallerCode(Model):
    """A code issued for an agent's page, in one env; claimed by one call."""

    __tablename__ = "caller_codes"

    agent: Mapped[str] = mapped_column(Text, primary_key=True)
    code: Mapped[str] = mapped_column(Text, primary_key=True)
    env: Mapped[Env] = mapped_column(StringEnum(Env), nullable=False)
    log: Mapped[CodeLog] = mapped_column(StringEnum(CodeLog), nullable=False)
    expires_at: Mapped[float] = mapped_column(Float, nullable=False)
    claimed: Mapped[str | None] = mapped_column(Text)


class CodeTry(Model):
    """How many codes a call keyed: three, then nothing it keys ties it to a page."""

    __tablename__ = "code_tries"
    __table_args__ = (Index("code_tries_first_at", "first_at"),)

    call: Mapped[str] = mapped_column(Text, primary_key=True)
    tries: Mapped[int] = mapped_column(Integer, nullable=False)
    first_at: Mapped[float] = mapped_column(Float, nullable=False)
