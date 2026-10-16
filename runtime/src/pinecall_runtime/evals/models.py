"""The evals tables: eval_runs, run_leases."""

from datetime import datetime
from typing import Any

from sqlalchemy import TIMESTAMP, Float, Index, Text, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from pinecall_runtime.enums import Env
from pinecall_runtime.kit.db import Model, StringEnum


class EvalRun(Model):
    """One run of an agent: every golden under every model, judged into its matrix as it goes."""

    __tablename__ = "eval_runs"
    __table_args__ = (
        Index("eval_runs_newest_first", text("started_at DESC")),
        Index("eval_runs_by_scope", "org", "env", text("started_at DESC")),
    )

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    agent: Mapped[str] = mapped_column(Text, nullable=False)
    started_at: Mapped[float] = mapped_column(Float, nullable=False)
    finished_at: Mapped[float | None] = mapped_column(Float)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    document: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    org: Mapped[str | None] = mapped_column(Text)
    env: Mapped[Env | None] = mapped_column(StringEnum(Env))


class RunLease(Model):
    """The run each agent is under; renewed while it runs, runs out on its own."""

    __tablename__ = "run_leases"

    agent: Mapped[str] = mapped_column(Text, primary_key=True)
    run: Mapped[str] = mapped_column(Text, nullable=False)
    until: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
