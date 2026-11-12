"""The org's monitors: one number of the series watched over a window, each fired at most once a day."""

import dataclasses
from collections import defaultdict
from collections.abc import Callable, Sequence
from datetime import date, timedelta
from typing import Protocol

from sqlalchemy.ext.asyncio import AsyncSession

from runtime.actor import THE_ORGS_OWN, Scope
from runtime.agents import service as agents
from runtime.alerts.models import Monitor
from runtime.alerts.repository import MonitorRepository
from runtime.alerts.service.alerts import Alerting
from runtime.enums import MonitorMetric, Stage
from runtime.exceptions import Conflict, NotFound
from runtime.kit.crypto import random_id
from runtime.kit.time import day_of
from runtime.wire.declaration import MonitorDeclared
from runtime.wire.events import MonitorFired

NO_SUCH_MONITOR = "no monitor {id} in this env: `pinecall monitors` lists them"
ID_PREFIX = "mon_"
# Who set a monitor its agent's class declares: the class keeps it, so no endpoint takes it out.
THE_CLASS = "class"
ITS_CLASS_WATCHES = "{name} is declared by the class of {agent}: take it out of the class, and the next call drops it"


# Whose a slug is, is whose its own log is, and the logs are calls', above alerts: what keeps the
# claims is handed in (agents declares the same need, and its getter hands out the one object).
class Owners(Protocol):
    """Who each agent belongs to."""

    async def owner(self, agent: str) -> str | None:
        """The org that claimed the agent's log, or None while nobody did."""
        ...


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
    return await MonitorRepository(session).list_of_env(scope.org, scope.env)


# A monitor of one agent watches an agent the org has; a slug typed wrong would never fire.
async def create_monitor(
    session: AsyncSession, owners: Owners, scope: Scope, wanted: MonitorDeclared, agent: str | None, *, by: str
) -> Monitor:
    """Watch a number: it fires, once a day, when it crosses the line over the window."""
    if agent is not None and await owners.owner(agent) != scope.org:
        raise agents.NoSuchAgent(agent)
    return await MonitorRepository(session).add(_monitor_of(scope, wanted, agent, by))


async def delete_monitor(session: AsyncSession, scope: Scope, monitor_id: str) -> None:
    """Stop watching; NotFound when the env has no such monitor."""
    repository = MonitorRepository(session)
    found = await repository.find(scope.org, scope.env, monitor_id)
    if found is None:
        raise NotFound(NO_SUCH_MONITOR.format(id=monitor_id))
    if found.created_by == THE_CLASS:
        raise Conflict(ITS_CLASS_WATCHES.format(name=found.name, agent=found.agent))
    await repository.delete(found)


def _monitor_of(scope: Scope, wanted: MonitorDeclared, agent: str | None, by: str) -> Monitor:
    return Monitor(
        id=random_id(ID_PREFIX, 6),
        org=scope.org,
        env=scope.env,
        agent=agent,
        name=wanted.name,
        metric=wanted.metric,
        above=wanted.above,
        threshold=wanted.threshold,
        window_days=wanted.window_days,
        created_by=by,
    )


# A monitor keeps the day it last fired, so the class's are rows too: made, changed and dropped by
# name as the class says them, at the seal of each of the agent's calls, before they are read.
async def sync_monitors(
    session: AsyncSession, scope: Scope, agent: str, wanted: Sequence[MonitorDeclared] | None
) -> list[Monitor]:
    """The agent's class's monitors as its class has them now (None leaves every row alone); the env's monitors."""
    repository = MonitorRepository(session)
    rows = list(await repository.list_of_env(scope.org, scope.env))
    if wanted is None:
        return rows
    kept = {row.name: row for row in rows if row.agent == agent and row.created_by == THE_CLASS}
    for each in wanted:
        row = kept.pop(each.name, None)
        if row is None:
            rows.append(await repository.add(_monitor_of(scope, each, agent, THE_CLASS), flush=False))
            continue
        row.metric, row.above, row.threshold, row.window_days = (
            each.metric,
            each.above,
            each.threshold,
            each.window_days,
        )
    for gone in kept.values():
        rows.remove(gone)
        await session.delete(gone)
    await session.flush()
    return rows


# ── read at every seal ──


# The env's monitors read the series over each one's window once the call is folded (the fold is
# what the series count). Each fires once a day, on the sealed call's agent's log, with the value
# that crossed. The rows are read once, and the series once for the monitors that share a window
# and an agent: a seal ran one query a monitor before.
async def check_monitors(
    session: AsyncSession,
    alerting: Alerting,
    scope: Scope,
    agent: str,
    *,
    series: Series,
    at: float,
    wanted: Sequence[MonitorDeclared] | None = None,
) -> None:
    """Say, once a day per monitor, that a number of the env crossed its line."""
    env_wide = dataclasses.replace(scope, holder=THE_ORGS_OWN)
    day = day_of(at)
    repository = MonitorRepository(session)
    reading: dict[tuple[int, str | None], list[Monitor]] = defaultdict(list)
    for monitor in await sync_monitors(session, scope, agent, wanted):
        reading[monitor.window_days, monitor.agent].append(monitor)
    for (window_days, watched), monitors in reading.items():
        days = await series(session, env_wide, day - timedelta(days=window_days - 1), day, watched)
        for monitor in monitors:
            value = measure(days, monitor.metric)
            if value is None or not crosses(monitor, value):
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
            await alerting.raise_alert(session, scope, agent, fired)


def crosses(monitor: Monitor, value: float) -> bool:
    """Whether the value is on the wrong side of the monitor's line."""
    return value > monitor.threshold if monitor.above else value < monitor.threshold


def measure(days: Sequence[SeriesDay], metric: MonitorMetric) -> float | None:
    """The metric over the window's days: sums, shares of sums, and latencies weighted by turns."""
    return MEASURES[metric](days)


def _count_calls(days: Sequence[SeriesDay]) -> float | None:
    return float(sum(day.calls for day in days))


def _sum_spend(days: Sequence[SeriesDay]) -> float | None:
    return sum(day.spent for day in days)


def _share_escalated(days: Sequence[SeriesDay]) -> float | None:
    calls = sum(day.calls for day in days)
    return None if calls == 0 else sum(day.escalated for day in days) / calls


def _share_held(days: Sequence[SeriesDay]) -> float | None:
    held = sum(judge.held for day in days for judge in day.judges)
    judged = sum(judge.judged for day in days for judge in day.judges)
    return None if judged == 0 else held / judged


def _share_of_tools_failing(days: Sequence[SeriesDay]) -> float | None:
    ran = sum(day.tools_ran for day in days)
    return None if ran == 0 else sum(day.tools_failed for day in days) / ran


def _median_e2e(days: Sequence[SeriesDay]) -> float | None:
    return _weigh([(day.e2e_median, day.calls) for day in days if day.e2e_median is not None])


def _median_llm(days: Sequence[SeriesDay]) -> float | None:
    known = [
        (stage.median_s, stage.turns)
        for day in days
        for stage in day.stages
        if stage.stage == Stage.llm and stage.median_s is not None
    ]
    return _weigh(known)


def _weigh(known: list[tuple[float, int]]) -> float | None:
    weight = sum(count for _, count in known)
    return None if weight == 0 else sum(value * count for value, count in known) / weight


MEASURES: dict[MonitorMetric, Callable[[Sequence[SeriesDay]], float | None]] = {
    MonitorMetric.calls: _count_calls,
    MonitorMetric.spend_usd: _sum_spend,
    MonitorMetric.escalated_rate: _share_escalated,
    MonitorMetric.held_rate: _share_held,
    MonitorMetric.tool_failure_rate: _share_of_tools_failing,
    MonitorMetric.e2e_median_s: _median_e2e,
    MonitorMetric.llm_median_s: _median_llm,
}
