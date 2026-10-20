"""A window of whole UTC days: the insights at a glance, the series, tools, slow turns, and an agent's drift."""

import re
from datetime import UTC, date, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Query

from pinecall_runtime.accounts.service import keys
from pinecall_runtime.agents.service import settings
from pinecall_runtime.billing import service as billing
from pinecall_runtime.calls.auth import CallsKey
from pinecall_runtime.calls.schemas import insights as schemas
from pinecall_runtime.calls.service import drift, slow_turns, tool_days, usage
from pinecall_runtime.calls.service.drift import Side, Tally
from pinecall_runtime.calls.service.usage import AgentWindow, WindowDay
from pinecall_runtime.enums import Stage
from pinecall_runtime.exceptions import ValidationError
from pinecall_runtime.postgres import Session

router = APIRouter()

# An org carries no timezone, so a day is cut in UTC and the answer says so.
TIMEZONE = "UTC"
# The windows the console offers, in whole UTC days: today, a week, a month.
WINDOW_DAYS = (1, 7, 30)
A_DAY_S = 86_400
A_VERSION = re.compile(r"v(\d+)")
NOT_A_WINDOW = "days={days} is not a window: one of 1, 7 or 30"
NOT_A_SIDE = "{text!r} is neither a day (YYYY-MM-DD) nor a version (v3)"
BOTH_SIDES = "a drift between versions names both: before=v3&after=v4"


# The window is the scope's, or one agent's of it; the budget is the org's across both envs and its
# month is the window's last day's, since it is one bill.
@router.get("/v1/insights")
async def insights(
    actor: CallsKey, session: Session, query: Annotated[schemas.InsightsQuery, Query()]
) -> schemas.Insights:
    """Whole UTC days of the key's env and scope at a glance, and the month's spend."""
    first, last = _window(query)
    if query.agent is not None:
        keys.check_agent(actor, query.agent)
    scope = actor.scope
    counted = await usage.counted_window(session, scope, _opening(first), _opening(last) + A_DAY_S, query.agent)
    quotas = await billing.get_quotas(session, actor.org, actor.env)
    stages = await drift.stages_of_window(session, scope, first, last, query.agent)
    return schemas.Insights(
        day=last.isoformat(),
        days=query.days,
        timezone=TIMEZONE,
        conversations=schemas.InsightsConversations(now=counted.calls, before=counted.before),
        resolved_rate=counted.unescalated / counted.finished if counted.finished else None,
        median_e2e_s=counted.median_e2e,
        spend_usd=counted.spent,
        channels=_channels(counted.channels),
        judged=counted.judged,
        passed=counted.passed,
        escalated=counted.escalated,
        mean_length_s=counted.mean_length,
        endings=[schemas.InsightsEnding(reason=reason, count=count) for reason, count in counted.endings],
        series=[_day(day) for day in counted.days],
        sessions_total=counted.total,
        live=counted.live,
        agents=[
            schemas.InsightsAgent(slug=agent.slug, calls=agent.calls, score=agent.score, spend=_spend(agent))
            for agent in counted.agents
        ],
        stages=[
            schemas.InsightsStage(
                stage=Stage(row.stage),
                vendor=row.vendor,
                model=row.model,
                turns=row.tally.turns,
                median_s=row.tally.median_s,
                p95_s=row.tally.p95_s,
                confidence=row.tally.confidence,
            )
            for row in stages
        ],
        budget=schemas.InsightsBudget(
            limit_usd=quotas.budget_usd, spent_usd_month=await billing.spent_in_month(session, actor.org, last)
        ),
    )


# What the Observability screen draws: the window's days, each in numbers, off the call index and
# the fold. The same query as /v1/insights.
@router.get("/v1/insights/series")
async def insights_series(
    actor: CallsKey, session: Session, query: Annotated[schemas.InsightsQuery, Query()]
) -> schemas.Series:
    """Every UTC day of the window: calls, endings, cost, latencies, judges and tools."""
    first, last = _window(query)
    if query.agent is not None:
        keys.check_agent(actor, query.agent)
    days = await usage.series_window(session, actor.scope, first, last, query.agent)
    vendors = await drift.stages_of_window(session, actor.scope, first, last, query.agent)
    return schemas.Series(
        day=last.isoformat(),
        days=query.days,
        agent=query.agent,
        timezone=TIMEZONE,
        series=[
            schemas.SeriesDay(
                day=day.day.isoformat(),
                calls=day.calls,
                finished=day.finished,
                escalated=day.escalated,
                spend_usd=day.spent,
                mean_length_s=day.mean_length,
                e2e_median_s=day.e2e_median,
                e2e_p95_s=day.e2e_p95,
                endings=[schemas.InsightsEnding(reason=reason, count=count) for reason, count in day.endings],
                stages=[
                    schemas.SeriesStage(stage=Stage(s.stage), turns=s.turns, median_s=s.median_s, p95_s=s.p95_s)
                    for s in day.stages
                ],
                judges=[schemas.SeriesJudge(name=j.name, held=j.held, judged=j.judged) for j in day.judges],
                tools_ran=day.tools_ran,
                tools_failed=day.tools_failed,
            )
            for day in days
        ],
        vendors=[
            schemas.SeriesVendor(
                stage=Stage(row.stage),
                vendor=row.vendor or "",
                model=row.model,
                turns=row.tally.turns,
                median_s=row.tally.median_s,
                p95_s=row.tally.p95_s,
            )
            for row in vendors
        ],
    )


# Folded when each call was sealed, like the series: one row per tool and day, added over the window.
@router.get("/v1/insights/tools")
async def insights_tools(
    actor: CallsKey, session: Session, query: Annotated[schemas.InsightsQuery, Query()]
) -> schemas.ToolsReport:
    """Every tool of the window: results, failures, median seconds and the newest failure."""
    first, last = _window(query)
    if query.agent is not None:
        keys.check_agent(actor, query.agent)
    tools = await tool_days.tools_of_window(session, actor.scope, first, last, query.agent)
    return schemas.ToolsReport(
        day=last.isoformat(),
        days=query.days,
        agent=query.agent,
        tools=[
            schemas.ToolStat(
                name=tool.name,
                ran=tool.ran,
                failed=tool.failed,
                median_s=tool.median_s,
                last_error=None
                if tool.last_error is None
                else schemas.ToolError(call=tool.last_error.call, at=tool.last_error.at, text=tool.last_error.text),
            )
            for tool in tools
        ],
    )


# Each call keeps its three slowest turns when it is sealed; this lists the window's slowest of them.
@router.get("/v1/insights/slow")
async def insights_slow(
    actor: CallsKey, session: Session, query: Annotated[schemas.SlowQuery, Query()]
) -> schemas.SlowTurns:
    """The slowest turns of the window with where each one's wait went, the slowest first."""
    first, last = _window(query)
    if query.agent is not None:
        keys.check_agent(actor, query.agent)
    turns = await slow_turns.slowest_of_window(session, actor.scope, first, last, query.agent, query.limit)
    return schemas.SlowTurns(
        day=last.isoformat(),
        days=query.days,
        agent=query.agent,
        turns=[schemas.SlowTurn.model_validate(turn, from_attributes=True) for turn in turns],
    )


# Folded when each call was sealed: two days or two versions read a few rows each.
@router.get("/v1/insights/drift")
async def insights_drift(
    actor: CallsKey, session: Session, query: Annotated[schemas.DriftQuery, Query()]
) -> schemas.Drift:
    """What moved between two days or versions of an agent, and the versions run or set."""
    keys.check_agent(actor, query.agent)
    scope = actor.scope
    before, after = _sides(query)
    tallies = (
        await drift.tally(session, scope, query.agent, before),
        await drift.tally(session, scope, query.agent, after),
    )
    judges, stages = drift.compared(*tallies)
    ran = tallies[0].versions | tallies[1].versions
    days = [side.day for side in (before, after) if side.day is not None]
    since = _midnight(min(days)) if days else datetime.fromtimestamp(0, UTC)
    until = _midnight(max(days)) + timedelta(days=1) if days else datetime.fromtimestamp(0, UTC)
    noted = await settings.versions_noted(session, scope, query.agent, ran, since, until)
    return schemas.Drift(
        agent=query.agent,
        world=scope.env,
        before=_side(before, tallies[0]),
        after=_side(after, tallies[1]),
        judges=[
            schemas.DriftJudge(
                name=judge.name,
                before=_judge_tally(judge.before),
                after=_judge_tally(judge.after),
                moved=judge.moved,
                criteria_changed=judge.criteria_changed,
            )
            for judge in judges
        ],
        stages=[
            schemas.DriftStage(
                stage=Stage(row.stage),
                vendor=row.vendor,
                model=row.model,
                before=_stage_tally(row.before),
                after=_stage_tally(row.after),
                median_moved_s=row.median_moved_s,
                p95_moved_s=row.p95_moved_s,
            )
            for row in stages
        ],
        versions=[
            schemas.DriftVersion(
                version=row.version,
                holder=row.holder,
                author=row.author,
                note=row.note,
                set_at=row.set_at.timestamp(),
                ran_before=row.version in tallies[0].versions,
                ran_after=row.version in tallies[1].versions,
            )
            for row in noted
        ],
    )


def _window(query: schemas.InsightsQuery) -> tuple[date, date]:
    if query.days not in WINDOW_DAYS:
        raise ValidationError(NOT_A_WINDOW.format(days=query.days))
    last = query.day or datetime.now(UTC).date()
    return last - timedelta(days=query.days - 1), last


# Two days by default: today and the day before it, in UTC.
def _sides(query: schemas.DriftQuery) -> tuple[Side, Side]:
    after = _side_of(query.after) if query.after is not None else Side(day=datetime.now(UTC).date())
    if query.before is not None:
        return _side_of(query.before), after
    if after.day is None:
        raise ValidationError(BOTH_SIDES)
    return Side(day=after.day - timedelta(days=1)), after


def _side_of(text: str) -> Side:
    version = A_VERSION.fullmatch(text)
    if version is not None:
        return Side(version=int(version.group(1)))
    try:
        return Side(day=date.fromisoformat(text))
    except ValueError as refused:
        raise ValidationError(NOT_A_SIDE.format(text=text)) from refused


def _side(side: Side, tallied: Tally) -> schemas.DriftSide:
    return schemas.DriftSide(
        day=None if side.day is None else side.day.isoformat(), version=side.version, versions=sorted(tallied.versions)
    )


def _judge_tally(read: drift.JudgeRead | None) -> schemas.JudgeTally | None:
    return None if read is None else schemas.JudgeTally(held=read.held, judged=read.judged, pass_rate=read.pass_rate)


def _stage_tally(tally: drift.StageTally | None) -> schemas.StageTally | None:
    if tally is None:
        return None
    return schemas.StageTally(
        turns=tally.turns, median_s=tally.median_s, p95_s=tally.p95_s, confidence=tally.confidence
    )


def _channels(counted: dict[str, int]) -> schemas.InsightsChannels:
    return schemas.InsightsChannels(phone=counted["phone"], web=counted["web"], whatsapp=counted["whatsapp"])


def _day(day: WindowDay) -> schemas.InsightsDay:
    return schemas.InsightsDay(
        day=day.day.isoformat(),
        phone=day.channels["phone"],
        web=day.channels["web"],
        whatsapp=day.channels["whatsapp"],
        spend_usd=day.spent,
        judged=day.judged,
        passed=day.passed,
    )


def _spend(agent: AgentWindow) -> schemas.InsightsSpend:
    total = sum(agent.spend.values())
    return schemas.InsightsSpend(
        llm_usd=agent.spend["llm"],
        stt_usd=agent.spend["stt"],
        tts_usd=agent.spend["tts"],
        phone_usd=agent.spend["phone"],
        platform_usd=agent.spend["platform"],
        minutes=round(agent.minutes, 3),
        per_minute_usd=round(total / agent.minutes, 6) if agent.minutes > 0 else None,
    )


def _opening(day: date) -> float:
    return _midnight(day).timestamp()


def _midnight(day: date) -> datetime:
    return datetime(day.year, day.month, day.day, tzinfo=UTC)
