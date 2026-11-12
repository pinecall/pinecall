"""Every column the vault seals, read a page at a time and rewritten row by row for a rotation of its key."""

from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from runtime.kit.db import Sealed, list_kept

# Where a column's first page starts: before any row of the table.
THE_START = "(0,0)"


@dataclass(frozen=True, slots=True)
class SealedColumn:
    """A column a secret is kept sealed in, by its table."""

    table: str
    column: str

    @property
    def named(self) -> str:
        """The column as a person reads it: table.column."""
        return f"{self.table}.{self.column}"


@dataclass(frozen=True, slots=True)
class SealedValue:
    """One sealed value of a column, and the row it is in."""

    row: str
    token: str


# No column is named here: a model types what the vault seals as `Sealed`, and this reads the types.
# Until 2026-11 the columns were a list of twelve names kept by hand.
def list_sealed_columns() -> list[SealedColumn]:
    """Every column of every table the vault seals, by table and column."""
    return [
        SealedColumn(table.name, column.name)
        for table, _ in list_kept()
        for column in table.columns
        if isinstance(column.type, Sealed)
    ]


# The tables share no key shape, so a row is named by its ctid, and rewritten only while it still
# holds the value read. The names are the models' own, never a caller's.
class SealedRepository:
    """The sealed values of one column."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_values(self, column: SealedColumn, *, after: str, page: int) -> list[SealedValue]:
        """One page of the column's sealed values past the row named, in the table's own order."""
        statement = text(
            f"SELECT ctid::text AS row, {column.column} AS token FROM {column.table} "
            f"WHERE {column.column} IS NOT NULL AND ctid > CAST(:after AS tid) ORDER BY ctid LIMIT :page"
        )
        rows = await self.session.execute(statement, {"after": after, "page": page})
        return [SealedValue(str(row), str(token)) for row, token in rows]

    async def reseal(self, column: SealedColumn, value: SealedValue, new: str) -> bool:
        """Rewrite one row's value, if the row is still where it was with the value read; whether it was."""
        statement = text(
            f"UPDATE {column.table} SET {column.column} = :new "
            f"WHERE ctid = CAST(:row AS tid) AND {column.column} = :old RETURNING 1"
        )
        changed = await self.session.execute(statement, {"new": new, "row": value.row, "old": value.token})
        return changed.first() is not None
