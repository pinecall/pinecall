"""Drift: each day's stage latencies and judges' verdicts by agent and config version, folded at the seal."""

from datetime import date
from typing import Any

from sqlalchemy import Date, Float, ForeignKey, Index, Integer, Text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from pinecall_runtime.enums import Env, Stage
from pinecall_runtime.kit.db import Model, StringEnum


class StageDay(Model):
    """A stage's seconds as a fixed histogram over one day, one vendor and model."""

    __tablename__ = "stage_days"
    __table_args__ = (Index("stage_days_by_version", "org", "env", "holder", "agent", "config_version"),)

    org: Mapped[str] = mapped_column(ForeignKey("orgs.id", ondelete="CASCADE"), primary_key=True)
    env: Mapped[Env] = mapped_column(StringEnum(Env), primary_key=True)
    holder: Mapped[str] = mapped_column(Text, primary_key=True)
    day: Mapped[date] = mapped_column(Date, primary_key=True)
    agent: Mapped[str] = mapped_column(Text, primary_key=True)
    config_version: Mapped[int] = mapped_column(Integer, primary_key=True)
    stage: Mapped[Stage] = mapped_column(StringEnum(Stage), primary_key=True)
    vendor: Mapped[str] = mapped_column(Text, primary_key=True)
    model: Mapped[str] = mapped_column(Text, primary_key=True)
    turns: Mapped[int] = mapped_column(Integer, nullable=False)
    buckets: Mapped[list[int]] = mapped_column(ARRAY(Integer), nullable=False)
    confidence_sum: Mapped[float] = mapped_column(Float, nullable=False)
    confidence_turns: Mapped[int] = mapped_column(Integer, nullable=False)


class JudgeDay(Model):
    """Each judge's settled verdicts over one day, under the hash of the question it asked."""

    __tablename__ = "judge_days"
    __table_args__ = (Index("judge_days_by_version", "org", "env", "holder", "agent", "config_version"),)

    org: Mapped[str] = mapped_column(ForeignKey("orgs.id", ondelete="CASCADE"), primary_key=True)
    env: Mapped[Env] = mapped_column(StringEnum(Env), primary_key=True)
    holder: Mapped[str] = mapped_column(Text, primary_key=True)
    day: Mapped[date] = mapped_column(Date, primary_key=True)
    agent: Mapped[str] = mapped_column(Text, primary_key=True)
    config_version: Mapped[int] = mapped_column(Integer, primary_key=True)
    judge: Mapped[str] = mapped_column(Text, primary_key=True)
    criteria: Mapped[str] = mapped_column(Text, primary_key=True)
    held: Mapped[int] = mapped_column(Integer, nullable=False)
    broken: Mapped[int] = mapped_column(Integer, nullable=False)


class DriftCall(Model):
    """One row per call folded, so a call judged again replaces its verdicts rather than adding."""

    __tablename__ = "drift_calls"
    __table_args__ = (Index("drift_calls_by_day", "org", "day"),)

    call: Mapped[str] = mapped_column(Text, primary_key=True)
    org: Mapped[str] = mapped_column(ForeignKey("orgs.id", ondelete="CASCADE"), nullable=False)
    env: Mapped[Env] = mapped_column(StringEnum(Env), nullable=False)
    holder: Mapped[str] = mapped_column(Text, nullable=False)
    agent: Mapped[str] = mapped_column(Text, nullable=False)
    day: Mapped[date] = mapped_column(Date, nullable=False)
    config_version: Mapped[int] = mapped_column(Integer, nullable=False)
    verdicts: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False)
    tools_ran: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    tools_failed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
