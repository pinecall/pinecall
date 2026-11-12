"""Each tool's day: a call's tool results counted by name at the seal, and read back over a window."""

import logging
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import date

from sqlalchemy.ext.asyncio import AsyncSession

from runtime.exceptions import ValidationError
from runtime.insights.repository.drift import Days, DriftRepository, ToolToAdd
from runtime.kit import histogram
from runtime.wire.base import Entry
from runtime.wire.parts import ToolResult

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class ToolError:
    """The newest failing result of a tool: the call, the moment it was written, its error."""

    call: str
    at: float
    text: str


@dataclass(frozen=True, slots=True)
class ToolTally:
    """One tool over a window: its results, its failures, its median seconds, its newest failure."""

    name: str
    ran: int
    failed: int
    median_s: float | None
    last_error: ToolError | None


@dataclass(frozen=True, slots=True)
class ToolsReport:
    """Every tool of a window, the most failed first: the window's last day, its days, whose agent."""

    day: date
    days: int
    agent: str | None
    tools: list[ToolTally]


@dataclass(slots=True)
class _Counted:
    ran: int = 0
    failed: int = 0
    seconds: list[float] = field(default_factory=list[float])
    last: ToolError | None = None


def rows_of(entries: Iterable[Entry]) -> list[ToolToAdd]:
    """A call's tool results counted by tool name, as the day's rows take them."""
    counted: dict[str, _Counted] = {}
    for entry in entries:
        result = _result_of(entry)
        if result is None:
            continue
        tool = counted.setdefault(result.name, _Counted())
        tool.ran += 1
        if result.duration_s is not None:
            tool.seconds.append(result.duration_s)
        if result.error is not None:
            tool.failed += 1
            # The newest failure stands; the same moment goes to the later entry.
            if tool.last is None or entry.ts >= tool.last.at:
                tool.last = ToolError(call=entry.call or "", at=entry.ts, text=result.error)
    return [
        ToolToAdd(
            tool=name,
            ran=tool.ran,
            failed=tool.failed,
            buckets=histogram.count_times(tool.seconds),
            last_error_call=None if tool.last is None else tool.last.call,
            last_error_at=None if tool.last is None else tool.last.at,
            last_error_text=None if tool.last is None else tool.last.text,
        )
        for name, tool in counted.items()
    ]


# Folded when each call was sealed, like the series: one row per tool and day, added over the window.
async def tools_of_window(session: AsyncSession, days: Days) -> ToolsReport:
    """Every tool of the window's days, days and agents added; most failed first."""
    sums: dict[str, tuple[int, int, list[int], ToolError | None]] = {}
    for row in await DriftRepository(session).list_tools(days):
        ran, failed, buckets, newest = sums.get(row.tool, (0, 0, histogram.empty(), None))
        failure = None
        if row.last_error_at is not None:
            failure = ToolError(call=row.last_error_call or "", at=row.last_error_at, text=row.last_error_text or "")
        if failure is not None and (newest is None or failure.at >= newest.at):
            newest = failure
        sums[row.tool] = (ran + row.ran, failed + row.failed, histogram.add(buckets, row.buckets), newest)
    tallies = [
        ToolTally(name, ran, failed, histogram.rank(buckets, histogram.MEDIAN), newest)
        for name, (ran, failed, buckets, newest) in sums.items()
    ]
    tallies.sort(key=lambda tool: (-tool.failed, -tool.ran, tool.name))
    return ToolsReport(day=days.last, days=days.count, agent=days.agent, tools=tallies)


def _result_of(entry: Entry) -> ToolResult | None:
    if entry.type != "tool.result":
        return None
    try:
        return ToolResult.parse(entry.data, entry.type)
    except ValidationError:
        logger.warning("call %s: seq %d is not a tool result drift reads", entry.call, entry.seq)
        return None
