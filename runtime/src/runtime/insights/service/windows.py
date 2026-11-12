"""A scope's window of whole UTC days in numbers: at a glance off the call index, and day by day for a chart."""

from collections.abc import Iterator, Sequence
from dataclasses import dataclass, field, replace
from datetime import date, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from runtime.actor import Scope
from runtime.billing import service as billing
from runtime.enums import Stage
from runtime.exceptions import ValidationError
from runtime.insights.models import StageDay
from runtime.insights.repository.drift import Days, DriftRepository
from runtime.insights.repository.series import AgentCounts, Ending, SeriesRepository, WindowDay
from runtime.insights.service import drift
from runtime.kit import histogram
from runtime.kit.time import now
from runtime.wire.declaration import WINDOWS

# An org carries no timezone, so a day is cut in UTC and the answer says so.
TIMEZONE = "UTC"
NOT_A_WINDOW = "days={days} is not a window: one of 1, 7 or 30"


@dataclass(frozen=True, slots=True)
class Conversations:
    """How many calls started in the window, and in the window of the same length before it."""

    now: int
    before: int


@dataclass(frozen=True, slots=True)
class Channels:
    """The window's calls by the channel they came in on."""

    phone: int
    web: int
    whatsapp: int


@dataclass(frozen=True, slots=True)
class Spend:
    """What one agent's window cost by stage, in US dollars, and per minute of its ended calls."""

    llm_usd: float
    stt_usd: float
    tts_usd: float
    phone_usd: float
    platform_usd: float
    minutes: float
    per_minute_usd: float | None


@dataclass(frozen=True, slots=True)
class AgentWindow:
    """One agent's window: its calls, the share of judgments it held, what it cost by stage."""

    slug: str
    calls: int
    score: float | None
    spend: Spend


@dataclass(frozen=True, slots=True)
class Budget:
    """What the org may spend in a month and what it has spent so far, both envs together."""

    limit_usd: int | None
    spent_usd_month: float


@dataclass(frozen=True, slots=True)
class WindowStage:
    """One stage over a window, versions added, by vendor and model: how slow, how sure the ears were."""

    stage: Stage
    vendor: str | None
    model: str | None
    turns: int
    median_s: float | None
    p95_s: float | None
    confidence: float | None


@dataclass(frozen=True, slots=True)
class Window:
    """A scope's window of whole UTC days at a glance, and the window of the same length before."""

    day: date
    days: int
    timezone: str
    conversations: Conversations
    # The share of the finished calls nobody escalated; None when none finished.
    resolved_rate: float | None
    median_e2e_s: float | None
    spend_usd: float
    channels: Channels
    judged: int
    passed: int
    escalated: int
    mean_length_s: float | None
    endings: list[Ending]
    series: list[WindowDay]
    # Every call of the scope, whenever it started, and those of them still open.
    sessions_total: int
    live: int
    agents: list[AgentWindow]
    stages: list[WindowStage]
    budget: Budget


@dataclass(frozen=True, slots=True)
class StageOfDay:
    """One stage over one day's turns: how many, and how slow at the median and the tail."""

    stage: Stage
    turns: int
    median_s: float | None
    p95_s: float | None


@dataclass(frozen=True, slots=True)
class JudgeOfDay:
    """One judge over one day: the verdicts that held, and those settled."""

    name: str
    held: int
    judged: int


# `spent` and `e2e_median` are the names alerts' monitors read a day by (`alerts.service.monitors`:
# `SeriesDay`): the wire's are `spend_usd` and `e2e_median_s`, and the body reads these two by alias.
@dataclass(frozen=True, slots=True)
class SeriesDay:
    """One UTC day of the window, every number a chart draws."""

    day: date
    calls: int = 0
    finished: int = 0
    escalated: int = 0
    spent: float = 0.0
    mean_length_s: float | None = None
    e2e_median: float | None = None
    e2e_p95_s: float | None = None
    endings: list[Ending] = field(default_factory=list[Ending])
    stages: list[StageOfDay] = field(default_factory=list[StageOfDay])
    judges: list[JudgeOfDay] = field(default_factory=list[JudgeOfDay])
    tools_ran: int = 0
    tools_failed: int = 0


@dataclass(frozen=True, slots=True)
class Series:
    """The window day by day, a quiet day included, and each stage of it by vendor and model."""

    day: date
    days: int
    agent: str | None
    timezone: str
    series: list[SeriesDay]
    vendors: list[WindowStage]


# The windows the console offers are whole UTC days: today, a week, a month.
def read_days(scope: Scope, last: date | None, count: int, agent: str | None) -> Days:
    """The window of so many whole UTC days of the scope ending on the day named, today when none is."""
    if count not in WINDOWS:
        raise ValidationError(NOT_A_WINDOW.format(days=count))
    end = last or now().date()
    return Days(scope, end - timedelta(days=count - 1), end, agent)


# The window is the scope's, or one agent's of it; the budget is the org's across both envs and its
# month is the window's last day's, since it is one bill.
async def window_of(session: AsyncSession, days: Days) -> Window:
    """Whole UTC days of the scope at a glance, counted off the call index, and the month's spend."""
    repository = SeriesRepository(session)
    counted = await repository.count_window(days)
    median_e2e_s = await repository.find_median_e2e(days)
    endings = await repository.list_endings(days)
    by_day = {row.day: row for row in await repository.list_days(days)}
    agents = await repository.list_agents(days)
    scope = days.scope
    quotas = await billing.get_quotas(session, scope.org, scope.env)
    stages = await stages_of_window(session, days)
    return Window(
        day=days.last,
        days=days.count,
        timezone=TIMEZONE,
        conversations=Conversations(now=counted.calls, before=counted.before),
        resolved_rate=counted.unescalated / counted.finished if counted.finished else None,
        median_e2e_s=median_e2e_s,
        spend_usd=counted.spend_usd,
        channels=Channels(counted.phone, counted.web, counted.whatsapp),
        judged=counted.judged,
        passed=counted.passed,
        escalated=counted.escalated,
        mean_length_s=counted.mean_length_s,
        endings=endings,
        # Every day of the window has its row, a day nobody called included, so a chart has no holes.
        series=[by_day.get(day, WindowDay(day)) for day in _each_day(days)],
        sessions_total=counted.total,
        live=counted.live,
        agents=[AgentWindow(agent.slug, agent.calls, agent.score, _spend_of(agent)) for agent in agents],
        stages=stages,
        budget=Budget(quotas.budget_usd, await billing.sum_spent(session, scope.org, days.last)),
    )


# What the Observability screen draws: the window's days, each in numbers, off the call index and
# the fold. A stage nobody named a vendor for is the vendor ''.
async def series_of(session: AsyncSession, days: Days) -> Series:
    """Every UTC day of the window: calls, endings, cost, latencies, judges and tools; and its vendors."""
    series = await _list_series(session, days)
    vendors = await stages_of_window(session, days)
    return Series(
        day=days.last,
        days=days.count,
        agent=days.agent,
        timezone=TIMEZONE,
        series=series,
        vendors=[replace(stage, vendor=stage.vendor or "") for stage in vendors],
    )


# Every agent's when the window names none; its days and versions are added together either way.
async def stages_of_window(session: AsyncSession, days: Days) -> list[WindowStage]:
    """Every stage of the window's days by vendor and model, versions added."""
    merged = drift.merge_stages(await DriftRepository(session).list_stages(days))
    return [
        WindowStage(
            stage=stage,
            vendor=vendor or None,
            model=model or None,
            turns=sample.turns,
            median_s=sample.median_s,
            p95_s=sample.p95_s,
            confidence=sample.confidence,
        )
        for (stage, vendor, model), sample in sorted(merged.items())
    ]


# What a monitor reads when a call is sealed (`alerts.service.monitors`: `Series`), handed in by the seal.
async def series_window(
    session: AsyncSession, scope: Scope, first: date, last: date, agent: str | None
) -> list[SeriesDay]:
    """Every UTC day from first to last, a quiet day included, in numbers."""
    return await _list_series(session, Days(scope, first, last, agent))


async def _list_series(session: AsyncSession, days: Days) -> list[SeriesDay]:
    counts, folds = SeriesRepository(session), DriftRepository(session)
    calls = {row.day: row for row in await counts.list_call_days(days)}
    e2e = {row.day: row for row in await counts.list_latency_days(days)}
    endings = await counts.list_day_endings(days)
    stages = await folds.list_stages(days)
    judges = await folds.list_judge_counts(days)
    tools = {row.day: row for row in await folds.list_tool_counts(days)}
    found: list[SeriesDay] = []
    for day in _each_day(days):
        counted, waited, ran = calls.get(day), e2e.get(day), tools.get(day)
        found.append(
            SeriesDay(
                day=day,
                calls=0 if counted is None else counted.calls,
                finished=0 if counted is None else counted.finished,
                escalated=0 if counted is None else counted.escalated,
                spent=0.0 if counted is None else counted.spend_usd,
                mean_length_s=None if counted is None else counted.mean_length_s,
                e2e_median=None if waited is None else waited.e2e_median_s,
                e2e_p95_s=None if waited is None else waited.e2e_p95_s,
                endings=endings.get(day, []),
                stages=_stages_of(day, stages),
                judges=[JudgeOfDay(row.judge, row.held, row.held + row.broken) for row in judges if row.day == day],
                tools_ran=0 if ran is None else ran.ran,
                tools_failed=0 if ran is None else ran.failed,
            )
        )
    return found


# A day's stage is every vendor and version of it added bucket by bucket, then read by rank.
def _stages_of(day: date, rows: Sequence[StageDay]) -> list[StageOfDay]:
    merged: dict[Stage, tuple[int, list[int]]] = {}
    for row in rows:
        if row.day != day:
            continue
        turns, buckets = merged.get(row.stage, (0, histogram.empty()))
        merged[row.stage] = (turns + row.turns, histogram.add(buckets, row.buckets))
    return [
        StageOfDay(
            stage=stage,
            turns=turns,
            median_s=histogram.rank(buckets, histogram.MEDIAN),
            p95_s=histogram.rank(buckets, histogram.P95),
        )
        for stage, (turns, buckets) in sorted(merged.items())
    ]


def _spend_of(agent: AgentCounts) -> Spend:
    total = agent.llm_usd + agent.stt_usd + agent.tts_usd + agent.phone_usd + agent.platform_usd
    return Spend(
        llm_usd=agent.llm_usd,
        stt_usd=agent.stt_usd,
        tts_usd=agent.tts_usd,
        phone_usd=agent.phone_usd,
        platform_usd=agent.platform_usd,
        minutes=round(agent.minutes, 3),
        per_minute_usd=round(total / agent.minutes, 6) if agent.minutes > 0 else None,
    )


def _each_day(days: Days) -> Iterator[date]:
    return (days.first + timedelta(days=n) for n in range(days.count))
