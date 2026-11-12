"""A scope's window counted off the call index: the counts over it, its agents and endings, and each UTC day's."""

from dataclasses import dataclass
from datetime import date
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import TextClause

from runtime.insights.repository.drift import Days
from runtime.kit.time import A_DAY_S, day_of

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


# `rest` is what follows the window: a condition more, the group, the order.
def _count(selected: str, *, by_day: bool = False, rest: str = "") -> TextClause:
    group = f"group by epoch_day{rest}" if by_day else rest
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

WINDOW_BY_AGENT = _count(
    """head.agent as slug, count(*) as calls,
       avg(f.held::double precision / f.judged) filter (where f.judged > 0) as score,
       coalesce(sum(f.cost_llm_usd), 0) as llm, coalesce(sum(f.cost_stt_usd), 0) as stt,
       coalesce(sum(f.cost_tts_usd), 0) as tts, coalesce(sum(f.cost_phone_usd), 0) as phone,
       coalesce(sum(f.cost_platform_usd), 0) as platform,
       coalesce(sum(f.ended_at - head.started_at) filter (where f.ended_at > head.started_at), 0) / 60 as minutes""",
    rest=" group by head.agent order by calls desc, slug",
)

WINDOW_ENDINGS = _count(
    "f.end_reason as reason, count(*) as counted",
    rest=" and f.end_reason is not null group by f.end_reason order by counted desc, reason",
)

WINDOW_BY_DAY = _count(
    """count(*) filter (where f.channel = 'phone') as phone,
       count(*) filter (where f.channel = 'web') as web,
       count(*) filter (where f.channel = 'whatsapp') as whatsapp,
       coalesce(sum(f.cost_usd), 0) as spent,
       count(*) filter (where f.judged > 0) as judged,
       count(*) filter (where f.judged > 0 and f.passed is not false) as passed""",
    by_day=True,
)

DAY_CALLS = _count(
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


@dataclass(frozen=True, slots=True)
class WindowCounts:
    """A window's calls counted: how many, how they went, what they cost, and the scope's calls beside them."""

    calls: int
    before: int
    finished: int
    unescalated: int
    judged: int
    passed: int
    escalated: int
    mean_length_s: float | None
    spend_usd: float
    phone: int
    web: int
    whatsapp: int
    # Every call of the scope, whenever it started, and those of them still open.
    total: int
    live: int


@dataclass(frozen=True, slots=True)
class AgentCounts:
    """One agent's calls of a window: the share of judgments it held, its dollars by stage, its minutes."""

    slug: str
    calls: int
    score: float | None
    llm_usd: float
    stt_usd: float
    tts_usd: float
    phone_usd: float
    platform_usd: float
    # The minutes of the calls that ended.
    minutes: float


@dataclass(frozen=True, slots=True)
class Ending:
    """One way calls ended, and how many did."""

    reason: str
    count: int


@dataclass(frozen=True, slots=True)
class WindowDay:
    """One UTC day of a window: its calls by channel, what they cost, and how their judges answered."""

    day: date
    phone: int = 0
    web: int = 0
    whatsapp: int = 0
    spend_usd: float = 0.0
    judged: int = 0
    passed: int = 0


@dataclass(frozen=True, slots=True)
class CallDay:
    """One UTC day's calls: how many started, finished and were escalated, their cost, their mean length."""

    day: date
    calls: int
    finished: int
    escalated: int
    spend_usd: float
    mean_length_s: float | None


@dataclass(frozen=True, slots=True)
class LatencyDay:
    """One UTC day's waits for first audio, over every turn: the median and the tail."""

    day: date
    e2e_median_s: float | None
    e2e_p95_s: float | None


class SeriesRepository:
    """The counts of a window and the rows of its days, each read a snapshot of its own."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def count_window(self, days: Days) -> WindowCounts:
        """The window's counts, one row."""
        row = (await self.session.execute(WINDOW, _params(days))).one()
        return WindowCounts(
            calls=int(row.calls),
            before=int(row.before),
            finished=int(row.finished),
            unescalated=int(row.unescalated),
            judged=int(row.judged),
            passed=int(row.passed),
            escalated=int(row.escalated),
            mean_length_s=None if row.mean_length is None else float(row.mean_length),
            spend_usd=float(row.spent),
            phone=int(row.phone),
            web=int(row.web),
            whatsapp=int(row.whatsapp),
            total=int(row.total),
            live=int(row.live),
        )

    async def find_median_e2e(self, days: Days) -> float | None:
        """The median of every turn's wait for first audio over the window."""
        return (await self.session.execute(WINDOW_MEDIAN_E2E, _params(days))).scalar_one_or_none()

    async def list_agents(self, days: Days) -> list[AgentCounts]:
        """One row per agent of the window, the busiest first: calls, score, cost by stage, minutes."""
        return [
            AgentCounts(
                slug=row.slug,
                calls=int(row.calls),
                score=row.score,
                llm_usd=float(row.llm),
                stt_usd=float(row.stt),
                tts_usd=float(row.tts),
                phone_usd=float(row.phone),
                platform_usd=float(row.platform),
                minutes=float(row.minutes),
            )
            for row in (await self.session.execute(WINDOW_BY_AGENT, _params(days))).all()
        ]

    async def list_endings(self, days: Days) -> list[Ending]:
        """How the window's calls ended, most frequent first."""
        rows = (await self.session.execute(WINDOW_ENDINGS, _params(days))).all()
        return [Ending(row.reason, int(row.counted)) for row in rows]

    async def list_days(self, days: Days) -> list[WindowDay]:
        """One row per UTC day of the window with calls: by channel, spent, judged, passed."""
        return [
            WindowDay(
                day=_day(row.epoch_day),
                phone=int(row.phone),
                web=int(row.web),
                whatsapp=int(row.whatsapp),
                spend_usd=float(row.spent),
                judged=int(row.judged),
                passed=int(row.passed),
            )
            for row in (await self.session.execute(WINDOW_BY_DAY, _params(days))).all()
        ]

    async def list_call_days(self, days: Days) -> list[CallDay]:
        """One row per UTC day with calls: calls, finished, escalated, spent, mean length."""
        return [
            CallDay(
                day=_day(row.epoch_day),
                calls=int(row.calls),
                finished=int(row.finished),
                escalated=int(row.escalated),
                spend_usd=float(row.spent),
                mean_length_s=None if row.mean_length is None else float(row.mean_length),
            )
            for row in (await self.session.execute(DAY_CALLS, _params(days))).all()
        ]

    async def list_latency_days(self, days: Days) -> list[LatencyDay]:
        """One row per UTC day with turns: the median and the p95 of first audio."""
        rows = (await self.session.execute(DAY_E2E, _params(days))).all()
        return [LatencyDay(_day(row.epoch_day), row.e2e_median, row.e2e_p95) for row in rows]

    async def list_day_endings(self, days: Days) -> dict[date, list[Ending]]:
        """How each UTC day's calls ended, most frequent first, by day."""
        found: dict[date, list[Ending]] = {}
        for row in (await self.session.execute(DAY_ENDINGS, _params(days))).all():
            found.setdefault(_day(row.epoch_day), []).append(Ending(row.reason, int(row.counted)))
        return found


def _params(days: Days) -> dict[str, Any]:
    scope = days.scope
    return {
        "org": scope.org,
        "env": scope.env.value,
        "holder": scope.holder,
        "start": days.start,
        "end": days.end,
        "agent": days.agent,
        "a_day": A_DAY_S,
    }


def _day(epoch_day: int) -> date:
    return day_of(int(epoch_day) * A_DAY_S)
