"""The live side's tables: the codes a caller keys, each call's tries of them, and the tokens a room was minted for."""

from datetime import datetime

from sqlalchemy import TIMESTAMP, Float, Index, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column

from runtime.enums import CodeLog, Env
from runtime.kit.db import Kept, Model, StringEnum, utc_now


class CallerCode(Model):
    """A code issued for an agent's page, in one env; claimed by one call."""

    __tablename__ = "caller_codes"
    __kept__ = Kept(
        agent="agent",
        not_exported="four digits that tie a call to a page for the minutes they live, swept as they expire",
        outlives="a code names its agent alone, and is deleted when it expires, minutes after it was issued",
    )

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
    __kept__ = Kept(
        call="call",
        not_exported="a count of the codes one call keyed, kept a day so a call cannot guess its way to a page",
        outlives="a count with nobody in it, forgotten a day after its call's first try",
    )

    call: Mapped[str] = mapped_column(Text, primary_key=True)
    tries: Mapped[int] = mapped_column(Integer, nullable=False)
    first_at: Mapped[float] = mapped_column(Float, nullable=False)


# The row names its org with no key to it, as the release before 2026-11 made the table: an org erased
# has its tokens deleted by the verb named here.
class Token(Model):
    """What a token was minted for, so the call that opens with it opens there and once."""

    __tablename__ = "tokens"
    __kept__ = Kept(
        call="call",
        agent="agent",
        not_exported="the ledger of the room tokens minted, each spent once: what a call was is in its log",
        erased_by="live.service.openings.delete_tokens",
    )

    call: Mapped[str] = mapped_column(Text, primary_key=True)
    org: Mapped[str] = mapped_column(Text, nullable=False)
    agent: Mapped[str] = mapped_column(Text, nullable=False)
    scope: Mapped[str] = mapped_column(Text, nullable=False)
    minted_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False, default=utc_now)
    expires_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    spent_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    # None on a token minted before the env was kept: held to its org and agent alone.
    env: Mapped[Env | None] = mapped_column(StringEnum(Env))
