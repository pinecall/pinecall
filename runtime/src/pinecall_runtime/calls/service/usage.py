"""What a scope used: a window of whole days in numbers, its series, and the metered feed."""

from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from pinecall_runtime.calls import histogram
from pinecall_runtime.calls.facts import STAGES
from pinecall_runtime.calls.metering import UsageRow, billed_row, usage_row
from pinecall_runtime.calls.repository.facts import FactsRepository
from pinecall_runtime.calls.repository.series import A_DAY_S, SeriesRepository
from pinecall_runtime.calls.store import Store
from pinecall_runtime.calls.writer import METERED_TYPES
from pinecall_runtime.enums import Channel
from pinecall_runtime.kit.auth import Scope
from pinecall_runtime.postgres import box_wide

CHANNELS = tuple(channel.value for channel in Channel)
SUMMARY = "call.summary"


@dataclass(frozen=True, slots=True)
class AgentWindow:
    """One agent's window: its calls, the share of judgments it held, what it cost by stage."""

    slug: str
    calls: int
    score: float | None
    # Dollars by stage (llm, stt, tts, phone, platform), and the minutes of the calls that ended.
    spend: dict[str, float]
    minutes: float


@dataclass(frozen=True, slots=True)
class WindowDay:
    """One UTC day of a window: its calls by channel, what they cost, and how their judges answered."""

    day: date
    channels: dict[str, int]
    spent: float
    judged: int
    passed: int


@dataclass(frozen=True, slots=True)
class Window:
    """A scope's window of whole UTC days in numbers, and the window of the same length before."""

    calls: int
    before: int
    finished: int
    unescalated: int
    judged: int
    passed: int
    escalated: int
    mean_length: float | None
    median_e2e: float | None
    spent: float
    channels: dict[str, int]
    endings: list[tuple[str, int]]
    days: list[WindowDay]
    agents: list[AgentWindow]
    total: int
    live: int


@dataclass(frozen=True, slots=True)
class MeteredPage:
    """One page of the usage feed: the rows kept, and the cursor past everything read."""

    rows: list[UsageRow]
    next: int | None


@dataclass(frozen=True, slots=True)
class StageDay:
    """One stage over one day's turns: how many, and how slow at the median and the tail."""

    stage: str
    turns: int
    median_s: float | None
    p95_s: float | None


@dataclass(frozen=True, slots=True)
class JudgeDay:
    """One judge over one day: the verdicts that held, and those settled."""

    name: str
    held: int
    judged: int


@dataclass(frozen=True, slots=True)
class SeriesDay:
    """One UTC day of the window, every number a chart draws."""

    day: date
    calls: int = 0
    finished: int = 0
    escalated: int = 0
    spent: float = 0.0
    mean_length: float | None = None
    e2e_median: float | None = None
    e2e_p95: float | None = None
    endings: list[tuple[str, int]] = field(default_factory=list[tuple[str, int]])
    stages: list[StageDay] = field(default_factory=list[StageDay])
    judges: list[JudgeDay] = field(default_factory=list[JudgeDay])
    tools_ran: int = 0
    tools_failed: int = 0


# The cursor moves past every row read, kept or not, so a page filtered to one org still moves.
async def metered_page(store: Store, session: AsyncSession, *, after: int, limit: int, org: str | None) -> MeteredPage:
    """The metered rows after the cursor, of one org or of every org, folded; a summary with what its
    facts keep of it: the vendors its call ran on the box's keys, and its simulated caller's cost."""
    read = [usage_row(item) for item in await store.across(METERED_TYPES, after=after, limit=limit)]
    kept = [row for row in read if org is None or row.org == org]
    return MeteredPage(rows=await _billed(session, kept), next=read[-1].cursor if read else None)


async def keep_caller_cost(session: AsyncSession, call: str, usd: float) -> None:
    """Add what a simulated caller's own model and voice cost to the call's facts, for the feed."""
    if usd > 0:
        await FactsRepository(session).add_caller_cost(call, usd)


async def keep_caller_played(session: AsyncSession, call: str, *, llm: str, tts: str | None, voice: str | None) -> None:
    """Keep who plays a simulated caller with the call's facts: its lines' model, its voice's, the voice."""
    await FactsRepository(session).keep_caller(call, {"caller_llm": llm, "caller_tts": tts, "caller_voice": voice})


# Not in the summary: the gateway keeps both with the call's facts — the lent vendors at the seal,
# the caller's cost when the simulation ends — and the log's wire stays the one every SDK reads.
async def _billed(session: AsyncSession, rows: list[UsageRow]) -> list[UsageRow]:
    calls = [row.call for row in rows if row.type == SUMMARY and row.call]
    if not calls:
        return rows
    with box_wide():
        billed = await FactsRepository(session).billed_of(calls)
    return [billed_row(row, *billed[row.call]) if row.type == SUMMARY and row.call in billed else row for row in rows]


# One agent's window when it names one; the whole scope's when it is None.
async def counted_window(session: AsyncSession, scope: Scope, start: float, end: float, agent: str | None) -> Window:
    """The scope's window from start to end, both on a UTC midnight, in numbers."""
    repository = SeriesRepository(session)
    params = SeriesRepository.params(scope, start, end, agent)
    counted = await repository.window(params)
    return Window(
        calls=int(counted.calls),
        before=int(counted.before),
        finished=int(counted.finished),
        unescalated=int(counted.unescalated),
        judged=int(counted.judged),
        passed=int(counted.passed),
        escalated=int(counted.escalated),
        mean_length=None if counted.mean_length is None else float(counted.mean_length),
        median_e2e=await repository.median_e2e(params),
        spent=float(counted.spent),
        channels={channel: int(getattr(counted, channel)) for channel in CHANNELS},
        endings=[(row.reason, int(row.counted)) for row in await repository.endings(params)],
        days=_every_day(start, end, {int(row.epoch_day): row for row in await repository.by_day(params)}),
        agents=[
            AgentWindow(
                slug=row.slug,
                calls=int(row.calls),
                score=row.score,
                spend={stage: float(getattr(row, stage)) for stage in STAGES},
                minutes=float(row.minutes),
            )
            for row in await repository.by_agent(params)
        ],
        total=int(counted.total),
        live=int(counted.live),
    )


async def series_window(
    session: AsyncSession, scope: Scope, first: date, last: date, agent: str | None
) -> list[SeriesDay]:
    """Every UTC day from first to last, a quiet day included, in numbers."""
    repository = SeriesRepository(session)
    params = SeriesRepository.params(scope, _opening(first), _opening(last) + A_DAY_S, agent)
    calls = {int(row.epoch_day): row for row in await repository.day_calls(params)}
    e2e = {int(row.epoch_day): row for row in await repository.day_e2e(params)}
    endings = await repository.day_endings(params)
    stages = await repository.day_stages(scope, first, last, agent)
    judges = await repository.day_judges(scope, first, last, agent)
    tools = {row.day: row for row in await repository.day_tools(scope, first, last, agent)}
    days = [first + timedelta(days=n) for n in range((last - first).days + 1)]
    found: list[SeriesDay] = []
    for day in days:
        epoch = _epoch(day)
        counted, waited, ran = calls.get(epoch), e2e.get(epoch), tools.get(day)
        found.append(
            SeriesDay(
                day=day,
                calls=0 if counted is None else int(counted.calls),
                finished=0 if counted is None else int(counted.finished),
                escalated=0 if counted is None else int(counted.escalated),
                spent=0.0 if counted is None else float(counted.spent),
                mean_length=None if counted is None or counted.mean_length is None else float(counted.mean_length),
                e2e_median=None if waited is None else waited.e2e_median,
                e2e_p95=None if waited is None else waited.e2e_p95,
                endings=[(row.reason, int(row.counted)) for row in endings if int(row.epoch_day) == epoch],
                stages=_stages_of(day, stages),
                judges=[
                    JudgeDay(row.judge, int(row.held), int(row.held) + int(row.broken))
                    for row in judges
                    if row.day == day
                ],
                tools_ran=0 if ran is None else int(ran.ran),
                tools_failed=0 if ran is None else int(ran.failed),
            )
        )
    return found


# A day's stage is every vendor and version of it added bucket by bucket, then read by rank.
def _stages_of(day: date, rows: Any) -> list[StageDay]:
    merged: dict[str, tuple[int, list[int]]] = {}
    for row in rows:
        if row.day != day:
            continue
        turns, buckets = merged.get(row.stage, (0, histogram.empty()))
        merged[row.stage] = (turns + int(row.turns), histogram.added(buckets, row.buckets))
    return [
        StageDay(
            stage=stage,
            turns=turns,
            median_s=histogram.rank(buckets, histogram.MEDIAN),
            p95_s=histogram.rank(buckets, histogram.P95),
        )
        for stage, (turns, buckets) in sorted(merged.items())
    ]


# Every day of the window has its row, a day nobody called included, so a chart has no holes.
def _every_day(start: float, end: float, counted: dict[int, Any]) -> list[WindowDay]:
    first, last = int(start // A_DAY_S), int(end // A_DAY_S)
    return [_day_of(epoch_day, counted.get(epoch_day)) for epoch_day in range(first, last)]


def _day_of(epoch_day: int, row: Any) -> WindowDay:
    day = datetime.fromtimestamp(epoch_day * A_DAY_S, UTC).date()
    if row is None:
        return WindowDay(day=day, channels=dict.fromkeys(CHANNELS, 0), spent=0.0, judged=0, passed=0)
    return WindowDay(
        day=day,
        channels={channel: int(getattr(row, channel)) for channel in CHANNELS},
        spent=float(row.spent),
        judged=int(row.judged),
        passed=int(row.passed),
    )


def _opening(day: date) -> float:
    return (day - date(1970, 1, 1)).days * float(A_DAY_S)


def _epoch(day: date) -> int:
    return (day - date(1970, 1, 1)).days
