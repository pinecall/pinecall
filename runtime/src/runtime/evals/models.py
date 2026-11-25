"""The evals tables: eval_runs, run_leases, comparisons, caller_jobs, judge_labels."""

from datetime import datetime
from typing import Any

from sqlalchemy import TIMESTAMP, Boolean, Float, ForeignKey, Index, Integer, Text, false
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


# A spoken simulation's caller is played by whichever process claims its row: the gateway that placed
# it, or a callers process beside the gateways. Until 2026-11-25 it was a coroutine of the gateway that
# took the request: nineteen of them on that one loop were late with their frames, and a release ended
# them all. The row is the caller from the moment its call has a place on its org's line until an hour
# after it ended; what an org wrote of it (who calls, about what) is its call's own, in `call_facts`.
class CallerJob(Model):
    """A simulated caller to play on a spoken call: placed by a gateway, claimed and played by one process."""

    __tablename__ = "caller_jobs"
    __table_args__ = (Index("caller_jobs_by_scope", "org", "env"), Index("caller_jobs_by_age", "placed_at"))
    __kept__ = Kept(
        call="call",
        agent="agent",
        not_exported="a caller's turn at a process, gone an hour after its call ended: nothing its call does not keep",
    )

    call: Mapped[str] = mapped_column(Text, primary_key=True)
    org: Mapped[str] = mapped_column(ForeignKey("orgs.id", ondelete="CASCADE"), nullable=False)
    env: Mapped[Env] = mapped_column(StringEnum(Env), nullable=False)
    agent: Mapped[str] = mapped_column(Text, nullable=False)
    comparison: Mapped[str | None] = mapped_column(Text)
    # The simulation as it was placed (`evals.service.caller_jobs`); NULL while its call is being
    # placed, when the row is the call's place on its org's line and nothing a process may claim.
    document: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    placed_at: Mapped[float] = mapped_column(Float, nullable=False)
    # The process that plays it, and when it last said so: one that stopped saying so left the call.
    claimed_by: Mapped[str | None] = mapped_column(Text)
    heard_at: Mapped[float | None] = mapped_column(Float)
    # How many processes took it: one let go before its call began is played whole by another, once.
    played: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    # Why its caller could not be played, said by its process before the call began: a gateway, which
    # has the live side, ends the call saying it.
    broke: Mapped[str | None] = mapped_column(Text)
    # When the job was over; and whether the call was left on the line by a process that stopped, which
    # a comparison places again.
    ended_at: Mapped[float | None] = mapped_column(Float)
    lost: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default=false())


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
