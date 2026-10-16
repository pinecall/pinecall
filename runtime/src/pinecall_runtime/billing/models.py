"""The billing tables: quotas, usage_totals."""

from datetime import date, datetime

from sqlalchemy import TIMESTAMP, BigInteger, Date, Float, ForeignKey, Integer, Text
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column

from pinecall_runtime.enums import Env
from pinecall_runtime.kit.db import Model, StringEnum, utc_now


class Quota(Model):
    """The quotas row: flows (minutes, messages), stocks (agents, numbers…), the budget, the lends."""

    __tablename__ = "quotas"

    org: Mapped[str] = mapped_column(ForeignKey("orgs.id", ondelete="CASCADE"), primary_key=True)
    env: Mapped[Env] = mapped_column(StringEnum(Env), primary_key=True)
    minutes: Mapped[int | None] = mapped_column(Integer)
    messages: Mapped[int | None] = mapped_column(Integer)
    agents: Mapped[int | None] = mapped_column(Integer)
    concurrent_calls: Mapped[int | None] = mapped_column(Integer)
    memory_facts: Mapped[int | None] = mapped_column(Integer)
    knowledge_chunks: Mapped[int | None] = mapped_column(Integer)
    numbers: Mapped[int | None] = mapped_column(Integer)
    seats: Mapped[int | None] = mapped_column(Integer)
    llm_tokens: Mapped[int | None] = mapped_column(BigInteger)
    hosted_apps: Mapped[int | None] = mapped_column(Integer)
    evals: Mapped[int | None] = mapped_column(Integer)
    simulations: Mapped[int | None] = mapped_column(Integer)
    # Whole US dollars a calendar month, both envs together.
    budget_usd: Mapped[int | None] = mapped_column(Integer)
    # Box vendor keys the org may use: NULL all, empty none, else `vendor` or `vendor/model`.
    lends: Mapped[list[str] | None] = mapped_column(ARRAY(Text))
    set_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False, default=utc_now)


class UsageTotal(Model):
    """The month's counts: calls, minutes, messages, tokens, characters, evals, simulations, cost."""

    __tablename__ = "usage_totals"

    org: Mapped[str] = mapped_column(Text, primary_key=True)
    env: Mapped[Env] = mapped_column(StringEnum(Env), primary_key=True)
    period: Mapped[date] = mapped_column(Date, primary_key=True)
    calls: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    minutes: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    messages: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    input_tokens: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    output_tokens: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    characters: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    evals: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    simulations: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    cost_usd: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
