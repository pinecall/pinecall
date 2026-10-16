"""The call_log rows: pages of a log, the whole of it, and the fed types across every log."""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from sqlalchemy import Row, select

from pinecall_runtime.calls.models import CallLog, CallLogHead
from pinecall_runtime.calls.schemas import DEFAULT_LIMIT
from pinecall_runtime.kit.repository import Repository
from pinecall_runtime.wire.base import Entry

COLUMNS = ("call", "seq", "ts", "agent", "type", "ephemeral", "data")


# position is the store's row order across every log; the meter resumes from it.
@dataclass(frozen=True, slots=True)
class Positioned:
    """An entry with its place in the whole store and the org its log belongs to."""

    position: int
    org: str | None
    entry: Entry


# Built, not validated: a row is what an Entry wrote, and its columns are typed, so validating it
# again re-checked our own write on every read, a tenth of a gateway's core at 300 calls (2026-10-01).
def entry_of(row: Row[*tuple[Any, ...]] | CallLog) -> Entry:
    """The entry a call_log row holds."""
    return Entry.model_construct(**{name: getattr(row, name) for name in COLUMNS})


class EntryRepository(Repository[CallLog]):
    """Reads of the log's rows; every write goes through the writer's own statements."""

    model = CallLog

    async def page(self, log: str, *, after: int = 0, limit: int = DEFAULT_LIMIT) -> list[Entry]:
        """One page of the log's durable entries above the cursor, in seq order."""
        statement = (
            select(*(getattr(CallLog, name) for name in COLUMNS))
            .where(CallLog.log == log, CallLog.seq > after)
            .order_by(CallLog.seq)
            .limit(limit)
        )
        return [entry_of(row) for row in (await self.session.execute(statement)).all()]

    async def whole(self, log: str, *, after: int = 0) -> list[Entry]:
        """Every durable entry of the log above the cursor, oldest first."""
        found: list[Entry] = []
        while True:
            page = await self.page(log, after=after, limit=DEFAULT_LIMIT)
            found += page
            if len(page) < DEFAULT_LIMIT:
                return found
            after = page[-1].seq

    # Served by call_log_metered (type, position).
    async def across(self, types: Sequence[str], *, after: int = 0, limit: int = DEFAULT_LIMIT) -> list[Positioned]:
        """One page of the entries of these types in every log, by position, with their owners."""
        statement = (
            select(CallLog.position, CallLogHead.org, *(getattr(CallLog, name) for name in COLUMNS))
            .join(CallLogHead, CallLogHead.log == CallLog.log)
            .where(CallLog.type.in_(list(types)), CallLog.position > after)
            .order_by(CallLog.position)
            .limit(limit)
        )
        rows = (await self.session.execute(statement)).all()
        return [Positioned(int(row.position), row.org, entry_of(row)) for row in rows]

    async def tool_answered(self, log: str, call_id: str) -> dict[str, Any] | None:
        """The data of the `tool.result` the log holds for this tool call id, or None."""
        statement = (
            select(CallLog.data)
            .where(CallLog.log == log, CallLog.type == "tool.result", CallLog.data["call_id"].astext == call_id)
            .order_by(CallLog.seq)
            .limit(1)
        )
        return (await self.session.execute(statement)).scalar_one_or_none()

    async def tool_called(self, log: str, call_id: str) -> Entry | None:
        """The `tool.call` entry the log holds for this tool call id, or None."""
        statement = (
            select(*(getattr(CallLog, name) for name in COLUMNS))
            .where(CallLog.log == log, CallLog.type == "tool.call", CallLog.data["call_id"].astext == call_id)
            .order_by(CallLog.seq)
            .limit(1)
        )
        row = (await self.session.execute(statement)).one_or_none()
        return None if row is None else entry_of(row)

    async def last_of_type(self, log: str, kind: str) -> Entry | None:
        """The newest entry of that type in the log, or None."""
        statement = (
            select(*(getattr(CallLog, name) for name in COLUMNS))
            .where(CallLog.log == log, CallLog.type == kind)
            .order_by(CallLog.seq.desc())
            .limit(1)
        )
        row = (await self.session.execute(statement)).one_or_none()
        return None if row is None else entry_of(row)
