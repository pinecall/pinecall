"""A window of whole UTC days: the insights at a glance, the series, tools, slow turns, and an agent's drift."""

from typing import Annotated

from fastapi import APIRouter, Query

from runtime.insights import schemas
from runtime.insights.auth import CallsKey, TheAllowedAgent, TheAllowedFilter
from runtime.insights.service import drift, slow_turns, tool_days, windows
from runtime.postgres import Session

router = APIRouter()


# The window is the scope's, or one agent's of it; the budget is the org's across both envs and its
# month is the window's last day's, since it is one bill.
@router.get("/v1/insights")
async def get_insights(
    actor: CallsKey, agent: TheAllowedFilter, session: Session, query: Annotated[schemas.InsightsQuery, Query()]
) -> schemas.Insights:
    """Whole UTC days of the key's env and scope at a glance, and the month's spend."""
    days = windows.read_days(actor.scope, query.day, query.days, agent)
    return schemas.Insights.of(await windows.window_of(session, days))


# What the Observability screen draws: the window's days, each in numbers, off the call index and
# the fold. The same query as /v1/insights.
@router.get("/v1/insights/series")
async def get_series(
    actor: CallsKey, agent: TheAllowedFilter, session: Session, query: Annotated[schemas.InsightsQuery, Query()]
) -> schemas.Series:
    """Every UTC day of the window: calls, endings, cost, latencies, judges and tools."""
    days = windows.read_days(actor.scope, query.day, query.days, agent)
    return schemas.Series.of(await windows.series_of(session, days))


# Folded when each call was sealed, like the series: one row per tool and day, added over the window.
@router.get("/v1/insights/tools")
async def list_tools(
    actor: CallsKey, agent: TheAllowedFilter, session: Session, query: Annotated[schemas.InsightsQuery, Query()]
) -> schemas.ToolsReport:
    """Every tool of the window: results, failures, median seconds and the newest failure."""
    days = windows.read_days(actor.scope, query.day, query.days, agent)
    return schemas.ToolsReport.of(await tool_days.tools_of_window(session, days))


# Each call keeps its three slowest turns when it is sealed; this lists the window's slowest of them.
@router.get("/v1/insights/slow")
async def list_slow_turns(
    actor: CallsKey, agent: TheAllowedFilter, session: Session, query: Annotated[schemas.SlowQuery, Query()]
) -> schemas.SlowTurns:
    """The slowest turns of the window with where each one's wait went, the slowest first."""
    days = windows.read_days(actor.scope, query.day, query.days, agent)
    return schemas.SlowTurns.of(await slow_turns.slowest_of_window(session, days, query.limit))


# Folded when each call was sealed: two days or two versions read a few rows each.
@router.get("/v1/insights/drift")
async def get_drift(
    actor: CallsKey, agent: TheAllowedAgent, session: Session, query: Annotated[schemas.DriftQuery, Query()]
) -> schemas.Drift:
    """What moved between two days or versions of an agent, and the versions run or set."""
    return schemas.Drift.of(await drift.drift_between(session, actor.scope, agent, query.before, query.after))
