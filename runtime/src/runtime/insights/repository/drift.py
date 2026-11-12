"""The drift tables: a sealed call claimed once, its stages, verdicts and tools added into its day, and read back."""

from collections.abc import Sequence
from dataclasses import asdict, dataclass
from datetime import date
from typing import Any

from sqlalchemy import ColumnElement, bindparam, func, select, text, update
from sqlalchemy.dialects.postgresql import JSONB, insert

from runtime.actor import Scope
from runtime.calls.models import CallLogHead
from runtime.enums import Env, Stage
from runtime.insights.models import DriftCall, JudgeDay, SlowTurn, StageDay, ToolDay
from runtime.kit.repository import Repository
from runtime.kit.time import A_DAY_S, opening_of

# Two histograms add bucket by bucket (kit/histogram); both always have its BUCKETS.
STAGES_ADDED = text("""
insert into stage_days as kept (org, env, holder, agent, day, config_version, stage, vendor,
                                model, turns, buckets, confidence_sum, confidence_turns)
select :org, :env, :holder, :agent, :day, :version, sample.stage,
       sample.vendor, sample.model, sample.turns, sample.buckets, sample.confidence_sum,
       sample.confidence_turns
from jsonb_to_recordset(:samples) as sample(stage text, vendor text, model text,
     turns integer, buckets integer[], confidence_sum double precision, confidence_turns integer)
on conflict (org, env, holder, day, agent, config_version, stage, vendor, model) do update set
    turns = kept.turns + excluded.turns,
    buckets = (select array_agg(mine + theirs order by at)
               from unnest(kept.buckets, excluded.buckets) with ordinality as bucket(mine, theirs, at)),
    confidence_sum = kept.confidence_sum + excluded.confidence_sum,
    confidence_turns = kept.confidence_turns + excluded.confidence_turns
""").bindparams(bindparam("samples", type_=JSONB))

# A verdict counted is +1 on its side; a verdict replaced is -1 on the side it was counted on.
VERDICTS_ADDED = text("""
insert into judge_days as kept (org, env, holder, agent, day, config_version, judge, criteria, held, broken)
select :org, :env, :holder, :agent, :day, :version, verdict.judge, verdict.criteria, verdict.held, verdict.broken
from jsonb_to_recordset(:verdicts) as verdict(judge text, criteria text, held integer, broken integer)
on conflict (org, env, holder, day, agent, config_version, judge, criteria) do update set
    held = kept.held + excluded.held,
    broken = kept.broken + excluded.broken
""").bindparams(bindparam("verdicts", type_=JSONB))

# A tool's results add into its day like a stage's; the newest failure of the two stands.
TOOLS_ADDED = text("""
insert into tool_days as kept (org, env, holder, agent, day, tool, ran, failed, buckets,
                               last_error_call, last_error_at, last_error_text)
select :org, :env, :holder, :agent, :day, found.tool, found.ran, found.failed, found.buckets,
       found.last_error_call, found.last_error_at, found.last_error_text
from jsonb_to_recordset(:tools) as found(tool text, ran integer, failed integer, buckets integer[],
     last_error_call text, last_error_at double precision, last_error_text text)
on conflict (org, env, holder, day, agent, tool) do update set
    ran = kept.ran + excluded.ran,
    failed = kept.failed + excluded.failed,
    buckets = (select array_agg(mine + theirs order by at)
               from unnest(kept.buckets, excluded.buckets) with ordinality as bucket(mine, theirs, at)),
    last_error_call = case when excluded.last_error_at is not null
                            and (kept.last_error_at is null or excluded.last_error_at >= kept.last_error_at)
                           then excluded.last_error_call else kept.last_error_call end,
    last_error_text = case when excluded.last_error_at is not null
                            and (kept.last_error_at is null or excluded.last_error_at >= kept.last_error_at)
                           then excluded.last_error_text else kept.last_error_text end,
    last_error_at = case when excluded.last_error_at is not null
                          and (kept.last_error_at is null or excluded.last_error_at >= kept.last_error_at)
                         then excluded.last_error_at else kept.last_error_at end
""").bindparams(bindparam("tools", type_=JSONB))

# A rebuild forgets what it will fold again, in one transaction, then folds call by call.
FORGET = text("""
with calls as (
    delete from drift_calls
    where (cast(:org as text) is null or org = :org) and (cast(:since as date) is null or day >= :since)
), stages as (
    delete from stage_days
    where (cast(:org as text) is null or org = :org) and (cast(:since as date) is null or day >= :since)
), tools as (
    delete from tool_days
    where (cast(:org as text) is null or org = :org) and (cast(:since as date) is null or day >= :since)
), slow as (
    delete from slow_turns
    where (cast(:org as text) is null or org = :org) and (cast(:since as date) is null or day >= :since)
)
delete from judge_days
where (cast(:org as text) is null or org = :org) and (cast(:since as date) is null or day >= :since)
""")

# The tables a call is folded into, each keyed by the scope, the agent and the day.
type Folded = type[StageDay] | type[JudgeDay] | type[ToolDay] | type[DriftCall] | type[SlowTurn]


@dataclass(frozen=True, slots=True)
class Where:
    """Which day's row a call is counted on: its scope, its agent, its day, its version."""

    org: str
    env: Env
    holder: str
    agent: str
    day: date
    version: int

    def params(self) -> dict[str, Any]:
        """As the statements take it."""
        return {
            "org": self.org,
            "env": self.env.value,
            "holder": self.holder,
            "agent": self.agent,
            "day": self.day,
            "version": self.version,
        }


# What a call's fold hands in: a value each, and the statement's own shape made of it here.
@dataclass(frozen=True, slots=True)
class StageToAdd:
    """One stage of a call on one vendor and model ('' for none): its turns, their seconds, the ears' confidence."""

    stage: Stage
    vendor: str
    model: str
    turns: int
    buckets: Sequence[int]
    confidence_sum: float
    confidence_turns: int


@dataclass(frozen=True, slots=True)
class VerdictsToAdd:
    """One judge's verdicts under one question's hash: how many more held, how many more broke."""

    judge: str
    criteria: str
    held: int
    broken: int


@dataclass(frozen=True, slots=True)
class ToolToAdd:
    """One tool of a call: its results, its failures, its seconds, and its newest failure."""

    tool: str
    ran: int
    failed: int
    buckets: Sequence[int]
    last_error_call: str | None
    last_error_at: float | None
    last_error_text: str | None


@dataclass(frozen=True, slots=True)
class TurnToKeep:
    """One slow turn of a call: when, how long the caller waited, and the parts of that wait."""

    call: str
    seq: int
    at: float
    name: str | None
    e2e_s: float
    hears_s: float | None
    thinks_s: float | None
    tools_s: float | None
    speaks_s: float | None


@dataclass(frozen=True, slots=True)
class Side:
    """One side of a drift: a day, a version, or both."""

    day: date | None = None
    version: int | None = None


# Days are cut in UTC: an org has no timezone.
@dataclass(frozen=True, slots=True)
class Days:
    """A window of a scope's whole UTC days, first to last: one agent's, or every agent's."""

    scope: Scope
    first: date
    last: date
    agent: str | None = None

    @property
    def count(self) -> int:
        """How many days the window holds."""
        return (self.last - self.first).days + 1

    @property
    def start(self) -> float:
        """The moment the first day opens, as seconds since the epoch."""
        return opening_of(self.first).timestamp()

    @property
    def end(self) -> float:
        """The moment the last day closes."""
        return opening_of(self.last).timestamp() + A_DAY_S


@dataclass(frozen=True, slots=True)
class JudgeCount:
    """One judge over one day of a window, every version and question added: its verdicts held and broken."""

    day: date
    judge: str
    held: int
    broken: int


@dataclass(frozen=True, slots=True)
class ToolCount:
    """The tools the calls of one day ran, and those that failed."""

    day: date
    ran: int
    failed: int


class DriftRepository(Repository[DriftCall]):
    """One row per sealed call counted, and the days its stages, verdicts, tools and slow turns added into."""

    model = DriftCall

    # ── a call counted ──

    # Taken once per call: a second fold of the same call finds its row and changes only what differs.
    async def claim(
        self, call: str, where: Where, verdicts: list[dict[str, Any]], tools_ran: int, tools_failed: int
    ) -> bool:
        """Count the call once; False when it was counted already."""
        statement = insert(DriftCall).values(
            call=call,
            org=where.org,
            env=where.env,
            holder=where.holder,
            agent=where.agent,
            day=where.day,
            config_version=where.version,
            verdicts=verdicts,
            tools_ran=tools_ran,
            tools_failed=tools_failed,
        )
        written = statement.on_conflict_do_nothing(index_elements=[DriftCall.call]).returning(DriftCall.call)
        return (await self.session.execute(written)).scalar_one_or_none() is not None

    async def lock_verdicts(self, call: str) -> list[dict[str, Any]] | None:
        """The verdicts the call was counted with, locked for a recount."""
        statement = select(DriftCall.verdicts).where(DriftCall.call == call).with_for_update()
        return (await self.session.execute(statement)).scalar_one_or_none()

    async def recount(self, call: str, verdicts: list[dict[str, Any]]) -> None:
        """Keep the verdicts the call is counted with now."""
        await self.session.execute(update(DriftCall).where(DriftCall.call == call).values(verdicts=verdicts))

    async def add_stages(self, where: Where, samples: Sequence[StageToAdd]) -> None:
        """Add the stage samples into the day's rows."""
        if samples:
            await self.session.execute(STAGES_ADDED, {**where.params(), "samples": _dump(samples)})

    async def add_verdicts(self, where: Where, verdicts: Sequence[VerdictsToAdd]) -> None:
        """Add the verdict counts into the day's rows."""
        if verdicts:
            await self.session.execute(VERDICTS_ADDED, {**where.params(), "verdicts": _dump(verdicts)})

    async def add_tools(self, where: Where, tools: Sequence[ToolToAdd]) -> None:
        """Add the tools' counts into the day's rows."""
        if tools:
            await self.session.execute(TOOLS_ADDED, {**where.params(), "tools": _dump(tools)})

    async def add_slow_turns(self, where: Where, turns: Sequence[TurnToKeep]) -> None:
        """Keep the call's slowest turns; a turn kept already stays as it is."""
        if turns:
            rows = [
                {"org": where.org, "env": where.env, "holder": where.holder, "agent": where.agent, "day": where.day}
                | asdict(turn)
                for turn in turns
            ]
            await self.session.execute(insert(SlowTurn).on_conflict_do_nothing(), rows)

    # ── two sides ──

    async def list_side_stages(self, scope: Scope, agent: str, side: Side) -> Sequence[StageDay]:
        """The stage rows of one side of an agent's drift."""
        statement = select(StageDay).where(*_of_agent(StageDay, scope, agent))
        if side.day is not None:
            statement = statement.where(StageDay.day == side.day)
        if side.version is not None:
            statement = statement.where(StageDay.config_version == side.version)
        return (await self.session.scalars(statement)).all()

    async def list_side_verdicts(self, scope: Scope, agent: str, side: Side) -> Sequence[JudgeDay]:
        """The judge rows of one side of an agent's drift."""
        statement = select(JudgeDay).where(*_of_agent(JudgeDay, scope, agent))
        if side.day is not None:
            statement = statement.where(JudgeDay.day == side.day)
        if side.version is not None:
            statement = statement.where(JudgeDay.config_version == side.version)
        return (await self.session.scalars(statement)).all()

    # ── a window of days ──

    async def list_stages(self, days: Days) -> Sequence[StageDay]:
        """Every stage row of the window's days."""
        return (await self.session.scalars(select(StageDay).where(*_in_days(StageDay, days)))).all()

    async def list_tools(self, days: Days) -> Sequence[ToolDay]:
        """Every tool row of the window's days."""
        return (await self.session.scalars(select(ToolDay).where(*_in_days(ToolDay, days)))).all()

    async def list_slowest_turns(self, days: Days, limit: int) -> Sequence[SlowTurn]:
        """The slowest turns of the window's days, slowest first."""
        statement = (
            select(SlowTurn)
            .where(*_in_days(SlowTurn, days))
            .order_by(SlowTurn.e2e_s.desc(), SlowTurn.at.desc(), SlowTurn.call, SlowTurn.seq)
            .limit(limit)
        )
        return (await self.session.scalars(statement)).all()

    async def list_judge_counts(self, days: Days) -> list[JudgeCount]:
        """Each judge's verdicts per day of the window, by day and judge."""
        statement = (
            select(JudgeDay.day, JudgeDay.judge, func.sum(JudgeDay.held), func.sum(JudgeDay.broken))
            .where(*_in_days(JudgeDay, days))
            .group_by(JudgeDay.day, JudgeDay.judge)
            .order_by(JudgeDay.day, JudgeDay.judge)
        )
        rows = (await self.session.execute(statement)).all()
        return [JudgeCount(day, judge, int(held), int(broken)) for day, judge, held, broken in rows]

    async def list_tool_counts(self, days: Days) -> list[ToolCount]:
        """The tools run and failed per day of the window."""
        statement = (
            select(DriftCall.day, func.sum(DriftCall.tools_ran), func.sum(DriftCall.tools_failed))
            .where(*_in_days(DriftCall, days))
            .group_by(DriftCall.day)
        )
        rows = (await self.session.execute(statement)).all()
        return [ToolCount(day, int(ran), int(failed)) for day, ran, failed in rows]

    # ── a rebuild ──

    async def forget(self, org: str | None, since: date | None) -> None:
        """Drop the drift of the calls named: an org's, those since a day, or every one."""
        await self.session.execute(FORGET, {"org": org, "since": since})

    async def list_sealed_after(self, org: str | None, since: float | None, after: str, limit: int) -> list[str]:
        """A page of the sealed, started calls past the cursor, for a rebuild."""
        statement = select(CallLogHead.log).where(
            CallLogHead.call.is_not(None),
            CallLogHead.sealed,
            CallLogHead.started_at.is_not(None),
            CallLogHead.log > after,
        )
        if org is not None:
            statement = statement.where(CallLogHead.org == org)
        if since is not None:
            statement = statement.where(CallLogHead.started_at >= since)
        rows = await self.session.execute(statement.order_by(CallLogHead.log).limit(limit))
        return [str(log) for log in rows.scalars()]


# As `jsonb_to_recordset` reads them: one object a value, its fields the record's columns.
def _dump(values: Sequence[StageToAdd | VerdictsToAdd | ToolToAdd]) -> list[dict[str, Any]]:
    return [asdict(value) for value in values]


def _of_agent(table: Folded, scope: Scope, agent: str) -> tuple[ColumnElement[bool], ...]:
    return (table.org == scope.org, table.env == scope.env, table.holder == scope.holder, table.agent == agent)


def _in_days(table: Folded, days: Days) -> tuple[ColumnElement[bool], ...]:
    scope = days.scope
    within = (
        table.org == scope.org,
        table.env == scope.env,
        table.holder == scope.holder,
        table.day >= days.first,
        table.day <= days.last,
    )
    return within if days.agent is None else (*within, table.agent == days.agent)
