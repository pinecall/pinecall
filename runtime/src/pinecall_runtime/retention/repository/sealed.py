"""Every column a secret is kept sealed in, read and rewritten row by row for a key rotation."""

from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


@dataclass(frozen=True, slots=True)
class SealedColumn:
    """A column a secret is kept sealed in, by its table."""

    table: str
    column: str

    @property
    def named(self) -> str:
        """The column as a person reads it: table.column."""
        return f"{self.table}.{self.column}"


# Every sealed column of the schema (models/*: `ciphertext`, `sealed`, `sealed_key`).
SEALED_COLUMNS: tuple[SealedColumn, ...] = (
    SealedColumn("box_settings", "ciphertext"),
    SealedColumn("call_private", "sealed"),
    SealedColumn("carriers", "ciphertext"),
    SealedColumn("hosted_apps", "sealed_key"),
    SealedColumn("one_use_words", "sealed"),
    SealedColumn("org_mail", "ciphertext"),
    SealedColumn("org_secrets", "sealed"),
    SealedColumn("org_sso", "ciphertext"),
    SealedColumn("org_telemetry", "ciphertext"),
    SealedColumn("org_webhooks", "ciphertext"),
    SealedColumn("provider_keys", "ciphertext"),
    SealedColumn("recording_keys", "sealed"),
)


# The tables share no key shape, so a row is named by its ctid, and rewritten only while it still
# holds the value read: a row written meanwhile is left for the next pass.
class SealedRepository:
    """The sealed values of one column."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def tokens(self, column: SealedColumn) -> list[tuple[str, str]]:
        """Each sealed value of the column, with the row's ctid."""
        statement = text(
            f"select ctid::text as row, {column.column} as token from {column.table} where {column.column} is not null"
        )
        return [(str(row), str(token)) for row, token in (await self.session.execute(statement)).all()]

    async def reseal(self, column: SealedColumn, row: str, old: str, new: str) -> int:
        """Rewrite one row's value, if it still holds the old one; how many rows changed (0 or 1)."""
        statement = text(
            f"update {column.table} set {column.column} = :new "
            f"where ctid = cast(:row as tid) and {column.column} = :old returning 1"
        )
        return len((await self.session.execute(statement, {"new": new, "row": row, "old": old})).all())
