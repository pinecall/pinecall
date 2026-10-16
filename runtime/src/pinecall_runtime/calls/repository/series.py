"""A scope's window in numbers: the counts over it, and each UTC day's series."""

from collections.abc import Sequence
from datetime import date
from typing import Any

from sqlalchemy import Row, text
from sqlalchemy.ext.asyncio import AsyncSession

from pinecall_runtime.kit.auth import Scope

# Days are cut in UTC: an org has no timezone.
A_DAY_S = 24 * 60 * 60

# The scope's calls, or one agent's when the window names one, inside the window.
CALLS = """
from call_log_head head left join call_facts f on f.call = head.log
where head.org = :org and head.env = :env and head.holder = :holder
  and head.call is not null and (cast(:agent as text) is null or head.agent = :agent)
"""
WINDOWED = "head.started_at >= :start and head.started_at < :end"
BY_DAY = "floor(head.started_at / :a_day)::bigint as epoch_day"

# The window's turns, one row each: unnested apart from the counts, or a call of ten turns would
# count ten times.
TURNS = """
from call_log_head head join call_facts f on f.call = head.log
cross join lateral unnest(f.e2e) as turn(seconds)
where head.org = :org and head.env = :env and head.holder = :holder
  and head.call is not null and (cast(:agent as text) is null or head.agent = :agent)
"""

# A table folded at the seal (stage_days, judge_days, drift_calls), read over the window's days.
FOLDED = """
where org = :org and env = :env and holder = :holder
  and day >= :first and day <= :last and (cast(:agent as text) is null or agent = :agent)
"""


def _counted(selected: str, *, by_day: bool = False, having: str = "") -> Any:
    group = f"group by epoch_day{having}" if by_day else having
    columns = f"{BY_DAY}, {selected}" if by_day else selected
    return text(f"select {columns} {CALLS} and {WINDOWED} {group}")


# "before" is the window of the same length right before it. A call is judged once a judge
# settled, and passed unless a judge said it did not.
WINDOW = text(f"""
select
    count(*) filter (where {WINDOWED}) as calls,
    count(*) filter (where head.started_at >= :start - (:end - :start) and head.started_at < :start) as before,
    count(*) filter (where {WINDOWED} and f.ended_at is not null) as finished,
    count(*) filter (where {WINDOWED} and f.ended_at is not null and not f.escalated) as unescalated,
    count(*) filter (where {WINDOWED} and f.judged > 0) as judged,
    count(*) filter (where {WINDOWED} and f.judged > 0 and f.passed is not false) as passed,
    count(*) filter (where {WINDOWED} and f.escalated) as escalated,
    avg(f.ended_at - head.started_at) filter (where {WINDOWED} and f.ended_at > head.started_at) as mean_length,
    coalesce(sum(f.cost_usd) filter (where {WINDOWED}), 0) as spent,
    count(*) filter (where {WINDOWED} and f.channel = 'phone') as phone,
    count(*) filter (where {WINDOWED} and f.channel = 'web') as web,
    count(*) filter (where {WINDOWED} and f.channel = 'whatsapp') as whatsapp,
    count(*) as total,
    count(*) filter (where not head.sealed) as live
{CALLS}
""")

WINDOW_MEDIAN_E2E = text(
    f"select percentile_cont(0.5) within group (order by turn.seconds) as median {TURNS} and {WINDOWED}"
)

WINDOW_BY_AGENT = _counted(
    """head.agent as slug, count(*) as calls,
       avg(f.held::double precision / f.judged) filter (where f.judged > 0) as score,
       coalesce(sum(f.cost_llm_usd), 0) as llm, coalesce(sum(f.cost_stt_usd), 0) as stt,
       coalesce(sum(f.cost_tts_usd), 0) as tts, coalesce(sum(f.cost_phone_usd), 0) as phone,
       coalesce(sum(f.cost_platform_usd), 0) as platform,
       coalesce(sum(f.ended_at - head.started_at) filter (where f.ended_at > head.started_at), 0) / 60 as minutes""",
    having=" group by head.agent order by calls desc, slug",
)

WINDOW_ENDINGS = _counted(
    "f.end_reason as reason, count(*) as counted",
    having=" and f.end_reason is not null group by f.end_reason order by counted desc, reason",
)

WINDOW_BY_DAY = _counted(
    """count(*) filter (where f.channel = 'phone') as phone,
       count(*) filter (where f.channel = 'web') as web,
       count(*) filter (where f.channel = 'whatsapp') as whatsapp,
       coalesce(sum(f.cost_usd), 0) as spent,
       count(*) filter (where f.judged > 0) as judged,
       count(*) filter (where f.judged > 0 and f.passed is not false) as passed""",
    by_day=True,
)

DAY_CALLS = _counted(
    """count(*) as calls,
       count(*) filter (where f.ended_at is not null) as finished,
       count(*) filter (where f.escalated) as escalated,
       coalesce(sum(f.cost_usd), 0) as spent,
       avg(f.ended_at - head.started_at) filter (where f.ended_at > head.started_at) as mean_length""",
    by_day=True,
)

DAY_ENDINGS = text(f"""
select {BY_DAY}, f.end_reason as reason, count(*) as counted {CALLS}
  and {WINDOWED} and f.end_reason is not null
group by epoch_day, f.end_reason
order by epoch_day, counted desc, reason
""")

DAY_E2E = text(f"""
select {BY_DAY},
       percentile_cont(0.5) within group (order by turn.seconds) as e2e_median,
       percentile_cont(0.95) within group (order by turn.seconds) as e2e_p95
{TURNS} and {WINDOWED}
group by epoch_day
""")

DAY_STAGES = text(f"select day, stage, turns, buckets from stage_days {FOLDED}")
DAY_JUDGES = text(
    f"select day, judge, sum(held) as held, sum(broken) as broken from judge_days {FOLDED} group by day, judge "
    f"order by day, judge"
)
DAY_TOOLS = text(
    f"select day, sum(tools_ran) as ran, sum(tools_failed) as failed from drift_calls {FOLDED} group by day"
)


class SeriesRepository:
    """The counts of a window and the rows of its days, each read a snapshot of its own."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    @staticmethod
    def params(scope: Scope, start: float, end: float, agent: str | None) -> dict[str, Any]:
        """What every window query takes."""
        return {
            "org": scope.org,
            "env": scope.env.value,
            "holder": scope.holder,
            "start": start,
            "end": end,
            "agent": agent,
            "a_day": A_DAY_S,
        }

    async def window(self, params: dict[str, Any]) -> Row[Any]:
        """The window's counts, one row."""
        return (await self.session.execute(WINDOW, params)).one()

    async def median_e2e(self, params: dict[str, Any]) -> float | None:
        """The median of every turn's wait for first audio over the window."""
        return (await self.session.execute(WINDOW_MEDIAN_E2E, params)).scalar_one_or_none()

    async def by_agent(self, params: dict[str, Any]) -> Sequence[Row[Any]]:
        """One row per agent of the window: calls, score, cost by stage, minutes."""
        return (await self.session.execute(WINDOW_BY_AGENT, params)).all()

    async def endings(self, params: dict[str, Any]) -> Sequence[Row[Any]]:
        """How the window's calls ended, most frequent first."""
        return (await self.session.execute(WINDOW_ENDINGS, params)).all()

    async def by_day(self, params: dict[str, Any]) -> Sequence[Row[Any]]:
        """One row per UTC day of the window with calls: by channel, spent, judged, passed."""
        return (await self.session.execute(WINDOW_BY_DAY, params)).all()

    async def day_calls(self, params: dict[str, Any]) -> Sequence[Row[Any]]:
        """One row per UTC day: calls, finished, escalated, spent, mean length."""
        return (await self.session.execute(DAY_CALLS, params)).all()

    async def day_e2e(self, params: dict[str, Any]) -> Sequence[Row[Any]]:
        """One row per UTC day: the median and the p95 of first audio."""
        return (await self.session.execute(DAY_E2E, params)).all()

    async def day_endings(self, params: dict[str, Any]) -> Sequence[Row[Any]]:
        """One row per UTC day and end reason."""
        return (await self.session.execute(DAY_ENDINGS, params)).all()

    async def day_stages(self, scope: Scope, first: date, last: date, agent: str | None) -> Sequence[Row[Any]]:
        """The stage_days rows of the window."""
        return (await self.session.execute(DAY_STAGES, _folded(scope, first, last, agent))).all()

    async def day_judges(self, scope: Scope, first: date, last: date, agent: str | None) -> Sequence[Row[Any]]:
        """Each judge's verdicts per day of the window."""
        return (await self.session.execute(DAY_JUDGES, _folded(scope, first, last, agent))).all()

    async def day_tools(self, scope: Scope, first: date, last: date, agent: str | None) -> Sequence[Row[Any]]:
        """The tools run and failed per day of the window."""
        return (await self.session.execute(DAY_TOOLS, _folded(scope, first, last, agent))).all()


def _folded(scope: Scope, first: date, last: date, agent: str | None) -> dict[str, Any]:
    return {
        "org": scope.org,
        "env": scope.env.value,
        "holder": scope.holder,
        "first": first,
        "last": last,
        "agent": agent,
    }
