"""The judging tables: the judges and personas an agent holds, the cases, the groups, the labels, the switches."""

from datetime import datetime
from typing import Any

from sqlalchemy import TIMESTAMP, Boolean, ForeignKey, Index, Integer, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from pinecall_runtime.enums import CaseSource, CaseStatus, Env, JudgeAnswer, JudgeRunsWhen
from pinecall_runtime.kit.db import Model, StringEnum, utc_now


class AgentJudge(Model):
    """How it answers, when it runs, what it reads beyond the call."""

    __tablename__ = "agent_judges"

    org: Mapped[str] = mapped_column(ForeignKey("orgs.id", ondelete="CASCADE"), primary_key=True)
    agent: Mapped[str] = mapped_column(Text, primary_key=True)
    name: Mapped[str] = mapped_column(Text, primary_key=True)
    question: Mapped[str] = mapped_column(Text, nullable=False)
    # Read no more; dropped by a later revision.
    runs_on: Mapped[str] = mapped_column(Text, nullable=False, default="every-call")
    author: Mapped[str] = mapped_column(Text, nullable=False, default="")
    set_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False, default=utc_now)
    answer: Mapped[JudgeAnswer] = mapped_column(StringEnum(JudgeAnswer), nullable=False, default=JudgeAnswer.verdict)
    choices: Mapped[list[Any]] = mapped_column(JSONB, nullable=False, default=list)
    runs_when: Mapped[JudgeRunsWhen] = mapped_column(
        StringEnum(JudgeRunsWhen), nullable=False, default=JudgeRunsWhen.always
    )
    trigger: Mapped[str] = mapped_column(Text, nullable=False, default="")
    reads: Mapped[list[Any]] = mapped_column(JSONB, nullable=False, default=list)


class AgentPersona(Model):
    """One agent's own persona, by name."""

    __tablename__ = "agent_personas"

    org: Mapped[str] = mapped_column(ForeignKey("orgs.id", ondelete="CASCADE"), primary_key=True)
    agent: Mapped[str] = mapped_column(Text, primary_key=True)
    name: Mapped[str] = mapped_column(Text, primary_key=True)
    about: Mapped[str] = mapped_column(Text, nullable=False, default="")
    goal: Mapped[str] = mapped_column(Text, nullable=False)
    style: Mapped[str] = mapped_column(Text, nullable=False)
    facts: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    state: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    author: Mapped[str] = mapped_column(Text, nullable=False, default="")
    set_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False, default=utc_now)
    llm: Mapped[str | None] = mapped_column(Text)
    tts: Mapped[str | None] = mapped_column(Text)
    voice: Mapped[str | None] = mapped_column(Text)
    # Read no more; dropped by a later revision.
    accepts_when: Mapped[str] = mapped_column(Text, nullable=False, default="")
    declines_when: Mapped[str] = mapped_column(Text, nullable=False, default="")
    expects: Mapped[list[Any]] = mapped_column(JSONB, nullable=False, default=list)
    tags: Mapped[list[Any]] = mapped_column(JSONB, nullable=False, default=list)
    behavior: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)


# The open group's predicate, a literal: an upsert inferring the index by a bound parameter fails
# once Postgres plans the prepared statement generically, after its fifth run on a connection.
OPEN_GROUP = "status = 'pending'"


class CaseGroup(Model):
    """One cause, one proposal, instead of fifty calls."""

    __tablename__ = "case_groups"
    __table_args__ = (
        Index(
            "case_groups_one_open",
            "org",
            "agent",
            "judge",
            unique=True,
            postgresql_where=OPEN_GROUP,
        ),
    )

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    org: Mapped[str] = mapped_column(ForeignKey("orgs.id", ondelete="CASCADE"), nullable=False)
    agent: Mapped[str] = mapped_column(Text, nullable=False)
    judge: Mapped[str] = mapped_column(Text, nullable=False)
    cause: Mapped[str] = mapped_column(Text, nullable=False, default="")
    status: Mapped[CaseStatus] = mapped_column(StringEnum(CaseStatus), nullable=False, default=CaseStatus.pending)
    since: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False, default=utc_now)
    proposal: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    proposed_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))


class EvalCase(Model):
    """Its golden, where it came from, what broke, and the group it joined."""

    __tablename__ = "eval_cases"
    __table_args__ = (
        UniqueConstraint("org", "agent", "name"),
        Index("eval_cases_by_call", "source_call"),
        Index("eval_cases_pending", "org", "agent", postgresql_where="status = 'pending'"),
        Index("eval_cases_by_group", "group_id", postgresql_where="group_id IS NOT NULL"),
    )

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    org: Mapped[str] = mapped_column(ForeignKey("orgs.id", ondelete="CASCADE"), nullable=False)
    agent: Mapped[str] = mapped_column(Text, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    golden: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    source_call: Mapped[str] = mapped_column(Text, nullable=False)
    source_env: Mapped[Env] = mapped_column(StringEnum(Env), nullable=False)
    held_out: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    author: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False, default=utc_now)
    status: Mapped[CaseStatus] = mapped_column(StringEnum(CaseStatus), nullable=False, default=CaseStatus.approved)
    broke: Mapped[list[Any]] = mapped_column(JSONB, nullable=False, default=list)
    source_version: Mapped[int | None] = mapped_column(Integer)
    kept_in_repo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    decided_by: Mapped[str | None] = mapped_column(Text)
    decided_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    group_id: Mapped[str | None] = mapped_column(ForeignKey("case_groups.id", ondelete="SET NULL"))
    source: Mapped[CaseSource] = mapped_column(StringEnum(CaseSource), nullable=False, default=CaseSource.call)
    persona: Mapped[str | None] = mapped_column(Text)


class JudgeLabel(Model):
    """Read against the verdict the seal counted, so a judge that disagrees with people is reported."""

    __tablename__ = "judge_labels"
    __table_args__ = (Index("judge_labels_by_org", "org", "env", "agent"),)

    call: Mapped[str] = mapped_column(Text, primary_key=True)
    judge: Mapped[str] = mapped_column(Text, primary_key=True)
    org: Mapped[str] = mapped_column(ForeignKey("orgs.id", ondelete="CASCADE"), nullable=False)
    env: Mapped[Env] = mapped_column(StringEnum(Env), nullable=False)
    agent: Mapped[str] = mapped_column(Text, nullable=False)
    held: Mapped[bool] = mapped_column(Boolean, nullable=False)
    note: Mapped[str | None] = mapped_column(Text)
    author: Mapped[str] = mapped_column(Text, nullable=False)
    labelled_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False, default=utc_now)


class JudgeSwitch(Model):
    """agent '' is the org's own switch; an agent's row wins over it."""

    __tablename__ = "judge_switches"

    org: Mapped[str] = mapped_column(ForeignKey("orgs.id", ondelete="CASCADE"), primary_key=True)
    agent: Mapped[str] = mapped_column(Text, primary_key=True, default="")
    name: Mapped[str] = mapped_column(Text, primary_key=True)
    is_on: Mapped[bool] = mapped_column(Boolean, nullable=False)
    author: Mapped[str] = mapped_column(Text, nullable=False, default="")
    set_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False, default=utc_now)


class PersonaSwitch(Model):
    """agent '' is the org's own switch; an agent's row wins over it."""

    __tablename__ = "persona_switches"

    org: Mapped[str] = mapped_column(ForeignKey("orgs.id", ondelete="CASCADE"), primary_key=True)
    agent: Mapped[str] = mapped_column(Text, primary_key=True, default="")
    name: Mapped[str] = mapped_column(Text, primary_key=True)
    is_on: Mapped[bool] = mapped_column(Boolean, nullable=False)
    author: Mapped[str] = mapped_column(Text, nullable=False, default="")
    set_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False, default=utc_now)
    # `vendor/model` the persona's lines are improvised on; NULL is the box's caller model.
    llm: Mapped[str | None] = mapped_column(Text)
    tts: Mapped[str | None] = mapped_column(Text)
    voice: Mapped[str | None] = mapped_column(Text)
