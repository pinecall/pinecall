"""The org's monitors: one number of the series watched over a window, each fired at most once a day."""

import dataclasses
from collections.abc import Callable, Sequence
from datetime import date, timedelta
from typing import Protocol

from sqlalchemy.ext.asyncio import AsyncSession

from pinecall_runtime.alerts.models import Monitor
from pinecall_runtime.alerts.repository import MonitorRepository
from pinecall_runtime.alerts.schemas import MonitorRequest
from pinecall_runtime.alerts.service.delivery import Logs, raise_alert
from pinecall_runtime.enums import MonitorMetric
from pinecall_runtime.exceptions import NotFound
from pinecall_runtime.kit.auth import THE_ORGS_OWN, Scope
from pinecall_runtime.kit.crypto import random_id
from pinecall_runtime.kit.handles import Handles
from pinecall_runtime.kit.time import day_of
from pinecall_runtime.wire.events import MonitorFired

NO_SUCH_MONITOR = "no monitor {id} in this env: `pinecall monitors` lists them"
LLM = "llm"


# The series is calls' read model, above alerts: the seal hands the function that reads it, and
# these are the shapes of what it answers that a measure reads.
class StageOfDay(Protocol):
    """One stage over one day's turns."""

    @property
    def stage(self) -> str:
        """Which stage: llm, stt, tts."""
        ...

    @property
    def turns(self) -> int:
        """How many turns it ran."""
        ...

    @property
    def median_s(self) -> float | None:
        """The median seconds, or None with no turn."""
        ...


class JudgeOfDay(Protocol):
    """One judge over one day."""

    @property
    def held(self) -> int:
        """Verdicts that held."""
        ...

    @property
    def judged(self) -> int:
        """Verdicts settled."""
        ...


class SeriesDay(Protocol):
    """One UTC day of the window, the numbers a monitor may watch."""

    @property
    def calls(self) -> int:
        """Calls started."""
        ...

    @property
    def escalated(self) -> int:
        """Calls escalated."""
        ...

    @property
    def spent(self) -> float:
        """Dollars spent."""
        ...

    @property
    def e2e_median(self) -> float | None:
        """The median end-to-end seconds, or None."""
        ...

    @property
    def stages(self) -> Sequence[StageOfDay]:
        """Each stage of the pipeline."""
        ...

    @property
    def judges(self) -> Sequence[JudgeOfDay]:
        """Each judge that ran."""
        ...

    @property
    def tools_ran(self) -> int:
        """Tool calls run."""
        ...

    @property
    def tools_failed(self) -> int:
        """Tool calls that failed."""
        ...


class Series(Protocol):
    """Every UTC day from first to last, in numbers, for the env and one agent or all."""

    async def __call__(
        self, session: AsyncSession, scope: Scope, first: date, last: date, agent: str | None
    ) -> Sequence[SeriesDay]:
        """The days, oldest first."""
        ...


# ── listed, set and dropped ──


async def list_monitors(session: AsyncSession, scope: Scope) -> Sequence[Monitor]:
    """Every monitor of the env, oldest first."""
    return await MonitorRepository(session).of_env(scope.org, scope.env)


async def create_monitor(session: AsyncSession, scope: Scope, wanted: MonitorRequest, *, by: str) -> Monitor:
    """Watch a number: it fires, once a day, when it crosses the line over the window."""
    monitor = Monitor(
        id=random_id("mon_", 6),
        org=scope.org,
        env=scope.env,
        agent=wanted.agent,
        name=wanted.name,
        metric=wanted.metric,
        above=wanted.above,
        threshold=wanted.threshold,
        window_days=wanted.window_days,
        created_by=by,
    )
    return await MonitorRepository(session).add(monitor)


async def delete_monitor(session: AsyncSession, scope: Scope, monitor_id: str) -> None:
    """Stop watching; NotFound when the env has no such monitor."""
    if not await MonitorRepository(session).drop(scope.org, scope.env, monitor_id):
        raise NotFound(NO_SUCH_MONITOR.format(id=monitor_id))


# ── read at every seal ──


# The env's monitors read the series over each one's window once the call is folded (the fold is
# what the series count). Each fires once a day, on the sealed call's agent's log, with the value
# that crossed.
async def check_monitors(
    session: AsyncSession, handles: Handles, logs: Logs, scope: Scope, agent: str, *, series: Series, at: float
) -> None:
    """Say, once a day per monitor, that a number of the env crossed its line."""
    env_wide = dataclasses.replace(scope, holder=THE_ORGS_OWN)
    day = day_of(at)
    repository = MonitorRepository(session)
    for monitor in await repository.of_env(scope.org, scope.env):
        first = day - timedelta(days=monitor.window_days - 1)
        value = measure(await series(session, env_wide, first, day, monitor.agent), monitor.metric)
        if value is None or not crossed(monitor, value):
            continue
        if not await repository.mark_fired(monitor.id, day, value):
            continue
        fired = MonitorFired(
            monitor=monitor.id,
            name=monitor.name,
            metric=monitor.metric,
            above=monitor.above,
            threshold=monitor.threshold,
            value=value,
            window_days=monitor.window_days,
            agent=monitor.agent,
            env=scope.env,
            day=day.isoformat(),
        )
        await raise_alert(session, handles, logs, scope, agent, fired)


def crossed(monitor: Monitor, value: float) -> bool:
    """Whether the value is on the wrong side of the monitor's line."""
    return value > monitor.threshold if monitor.above else value < monitor.threshold


def measure(days: Sequence[SeriesDay], metric: MonitorMetric) -> float | None:
    """The metric over the window's days: sums, shares of sums, and latencies weighted by turns."""
    return MEASURES[metric](days)


def _calls(days: Sequence[SeriesDay]) -> float | None:
    return float(sum(day.calls for day in days))


def _spend(days: Sequence[SeriesDay]) -> float | None:
    return sum(day.spent for day in days)


def _escalated_rate(days: Sequence[SeriesDay]) -> float | None:
    calls = sum(day.calls for day in days)
    return None if calls == 0 else sum(day.escalated for day in days) / calls


def _held_rate(days: Sequence[SeriesDay]) -> float | None:
    held = sum(judge.held for day in days for judge in day.judges)
    judged = sum(judge.judged for day in days for judge in day.judges)
    return None if judged == 0 else held / judged


def _tool_failure_rate(days: Sequence[SeriesDay]) -> float | None:
    ran = sum(day.tools_ran for day in days)
    return None if ran == 0 else sum(day.tools_failed for day in days) / ran


def _e2e_median(days: Sequence[SeriesDay]) -> float | None:
    return _weighted([(day.e2e_median, day.calls) for day in days if day.e2e_median is not None])


def _llm_median(days: Sequence[SeriesDay]) -> float | None:
    known = [
        (stage.median_s, stage.turns)
        for day in days
        for stage in day.stages
        if stage.stage == LLM and stage.median_s is not None
    ]
    return _weighted(known)


def _weighted(known: list[tuple[float, int]]) -> float | None:
    weight = sum(count for _, count in known)
    return None if weight == 0 else sum(value * count for value, count in known) / weight


MEASURES: dict[MonitorMetric, Callable[[Sequence[SeriesDay]], float | None]] = {
    MonitorMetric.calls: _calls,
    MonitorMetric.spend_usd: _spend,
    MonitorMetric.escalated_rate: _escalated_rate,
    MonitorMetric.held_rate: _held_rate,
    MonitorMetric.tool_failure_rate: _tool_failure_rate,
    MonitorMetric.e2e_median_s: _e2e_median,
    MonitorMetric.llm_median_s: _llm_median,
}
