"""The call_private rows: the values a log masked, sealed, by log and seq."""

from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from runtime.calls.models import CallLog, CallPrivate
from runtime.calls.repository.entries import COLUMNS, entry_of
from runtime.kit.repository import Repository
from runtime.wire.base import Entry


class PrivateRepository(Repository[CallPrivate]):
    """One row per entry that held a private value: the values, sealed under the vault key."""

    model = CallPrivate

    async def keep(self, log: str, rows: Sequence[tuple[int, str]]) -> None:
        """Seal the private values of these entries of the log, by seq; one kept already stays."""
        if not rows:
            return
        statement = insert(CallPrivate).values([{"log": log, "seq": seq, "sealed": sealed} for seq, sealed in rows])
        await self.session.execute(statement.on_conflict_do_nothing(index_elements=[CallPrivate.log, CallPrivate.seq]))

    async def list_of_log(self, log: str) -> dict[int, str]:
        """Every sealed value of the log, by seq."""
        statement = select(CallPrivate.seq, CallPrivate.sealed).where(CallPrivate.log == log)
        return {int(seq): str(sealed) for seq, sealed in (await self.session.execute(statement)).all()}

    async def list_of_tool_calls(self, log: str, after: int) -> list[tuple[Entry, str]]:
        """The tool.call entries of the log above `after` that kept private values, each with them sealed."""
        statement = (
            select(*(getattr(CallLog, name) for name in COLUMNS), CallPrivate.sealed)
            .join(CallPrivate, (CallPrivate.log == CallLog.log) & (CallPrivate.seq == CallLog.seq))
            .where(CallLog.log == log, CallLog.type == "tool.call", CallLog.seq > after)
            .order_by(CallLog.seq)
        )
        return [(entry_of(row), str(row.sealed)) for row in (await self.session.execute(statement)).all()]

    async def find_of_entry(self, log: str, seq: int) -> str | None:
        """The sealed value of one entry, or None when it kept none."""
        statement = select(CallPrivate.sealed).where(CallPrivate.log == log, CallPrivate.seq == seq)
        return (await self.session.execute(statement)).scalar_one_or_none()
