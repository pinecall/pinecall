"""The call_log rows: pages of a log, the whole of it, the fed types across every log, a tool's call and its answer."""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Literal

from sqlalchemy import Row, select

from runtime.calls.models import CallLog, CallLogHead, Opener
from runtime.kit.repository import Repository
from runtime.wire.base import Entry

COLUMNS = ("call", "seq", "ts", "agent", "type", "ephemeral", "data")

# One page of a log, wherever a log is read by pages: a reader's backlog, the relay reading the
# store while the signal is down, a rebuild. Until 2026-11 it was the HTTP layer's default limit,
# imported here from the schemas.
A_PAGE = 500

# The two entries of one tool call: the question and its answer, found by the call id they share.
type ToolEntry = Literal["tool.call", "tool.result"]


# position is the store's row order across every log; the meter resumes from it.
@dataclass(frozen=True, slots=True)
class Positioned:
    """An entry with its place in the whole store, the org its log belongs to and who opened that log."""

    position: int
    org: str | None
    entry: Entry
    opened_by: Opener | None = None


# Built, not validated: a row is what an Entry wrote, and its columns are typed, so validating it
# again re-checked our own write on every read, a tenth of a gateway's core at 300 calls (2026-10-01).
def entry_of(row: Row[*tuple[Any, ...]] | CallLog) -> Entry:
    """The entry a call_log row holds."""
    return Entry.model_construct(**{name: getattr(row, name) for name in COLUMNS})


class EntryRepository(Repository[CallLog]):
    """Reads of the log's rows; every write goes through the writer's own statements."""

    model = CallLog

    async def page_of(self, log: str, *, after: int = 0, limit: int = A_PAGE) -> list[Entry]:
        """One page of the log's durable entries above the cursor, in seq order."""
        statement = (
            select(*(getattr(CallLog, name) for name in COLUMNS))
            .where(CallLog.log == log, CallLog.seq > after)
            .order_by(CallLog.seq)
            .limit(limit)
        )
        return [entry_of(row) for row in (await self.session.execute(statement)).all()]

    async def whole_of(self, log: str, *, after: int = 0) -> list[Entry]:
        """Every durable entry of the log above the cursor, oldest first."""
        found: list[Entry] = []
        while True:
            page = await self.page_of(log, after=after, limit=A_PAGE)
            found += page
            if len(page) < A_PAGE:
                return found
            after = page[-1].seq

    # Served by call_log_metered (type, position). The positions come in commit order for the fed
    # types alone (`log/writer.py`: `FED_TYPES`): the store refuses any other before it asks.
    async def list_across(self, types: Sequence[str], *, after: int = 0, limit: int = A_PAGE) -> list[Positioned]:
        """One page of the entries of these types in every log, by position, with their owners."""
        statement = (
            select(
                CallLog.position, CallLogHead.org, CallLogHead.opened_by, *(getattr(CallLog, name) for name in COLUMNS)
            )
            .join(CallLogHead, CallLogHead.log == CallLog.log)
            .where(CallLog.type.in_(list(types)), CallLog.position > after)
            .order_by(CallLog.position)
            .limit(limit)
        )
        rows = (await self.session.execute(statement)).all()
        return [Positioned(int(row.position), row.org, entry_of(row), row.opened_by) for row in rows]

    async def find_of_tool(self, log: str, kind: ToolEntry, call_id: str) -> Entry | None:
        """The `tool.call` or the `tool.result` entry the log holds for this tool call id, or None."""
        statement = (
            select(*(getattr(CallLog, name) for name in COLUMNS))
            .where(CallLog.log == log, CallLog.type == kind, CallLog.data["call_id"].astext == call_id)
            .order_by(CallLog.seq)
            .limit(1)
        )
        row = (await self.session.execute(statement)).one_or_none()
        return None if row is None else entry_of(row)
