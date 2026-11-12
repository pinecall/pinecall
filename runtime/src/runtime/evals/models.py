"""The evals tables: eval_runs, run_leases, comparisons, judge_labels."""

from datetime import datetime
from typing import Any

from sqlalchemy import TIMESTAMP, Boolean, Float, ForeignKey, Index, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from runtime.enums import Env
from runtime.kit.db import Kept, Model, StringEnum, descending, utc_now


# The row names its org with no key to it (a run written before orgs had one has none), so the org's
# erasure reaches it by evals' own verb.
class EvalRun(Model):
    """One run of an agent: every golden under every model, judged into its matrix as it goes."""

    __tablename__ = "eval_runs"
    __table_args__ = (
        Index("eval_runs_newest_first", descending("started_at")),
        Index("eval_runs_by_scope", "org", "env", descending("started_at")),
    )
    __kept__ = Kept(
        agent="agent",
        exported=("id", "agent", "started_at", "finished_at", "status", "document"),
        erased_by="evals.service.runs.delete_runs",
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
    __kept__ = Kept(
        agent="agent",
        not_exported="a lease of a minute on an agent's name: nothing an org wrote",
        outlives="a lease names its agent alone and runs out a minute after its run stops renewing it",
    )

    agent: Mapped[str] = mapped_column(Text, primary_key=True)
    run: Mapped[str] = mapped_column(Text, nullable=False)
    until: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)


# The calls of a comparison are rows of call_facts under its id. This row is what those cannot say:
# what was asked for, so a call not placed yet has its place on the board, and what was refused.
# Until 2026-11 an agent erased left its comparisons behind, with its personas and its refusals: the
# row names its agent here, so the erasure of an agent finds it.
class Comparison(Model):
    """One comparison as it was asked for: its callers, its setups, its repeats, and how its placing stands."""

    __tablename__ = "comparisons"
    __table_args__ = (Index("comparisons_by_scope", "org", "env", descending("started_at")),)
    __kept__ = Kept(agent="agent", exported=("id", "agent", "started_at", "document"))

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    org: Mapped[str] = mapped_column(ForeignKey("orgs.id", ondelete="CASCADE"), nullable=False)
    env: Mapped[Env] = mapped_column(StringEnum(Env), nullable=False)
    agent: Mapped[str] = mapped_column(Text, nullable=False)
    started_at: Mapped[float] = mapped_column(Float, nullable=False)
    document: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)


class JudgeLabel(Model):
    """Read against the verdict the seal counted, so a judge that disagrees with people is reported."""

    __tablename__ = "judge_labels"
    __table_args__ = (Index("judge_labels_by_org", "org", "env", "agent"),)
    __kept__ = Kept(
        call="call",
        agent="agent",
        exported=("call", "judge", "agent", "held", "note", "author", "labelled_at"),
    )

    call: Mapped[str] = mapped_column(Text, primary_key=True)
    judge: Mapped[str] = mapped_column(Text, primary_key=True)
    org: Mapped[str] = mapped_column(ForeignKey("orgs.id", ondelete="CASCADE"), nullable=False)
    env: Mapped[Env] = mapped_column(StringEnum(Env), nullable=False)
    agent: Mapped[str] = mapped_column(Text, nullable=False)
    held: Mapped[bool] = mapped_column(Boolean, nullable=False)
    note: Mapped[str | None] = mapped_column(Text)
    author: Mapped[str] = mapped_column(Text, nullable=False)
    labelled_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False, default=utc_now)
