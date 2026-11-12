"""The vault's key rotated: every value every table keeps sealed, sealed again under the newest key, and counted."""

from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from runtime.exceptions import ServiceUnavailable
from runtime.kit.crypto import Vault
from runtime.platform.repository.sealed import (
    THE_START,
    SealedColumn,
    SealedRepository,
    SealedValue,
    list_sealed_columns,
)

# How many of a column's values are read at a time.
A_PAGE_OF_VALUES = 500


@dataclass(frozen=True, slots=True)
class Resealed:
    """One column after a pass: sealed again now, already under the newest key, opened by no key, moved meanwhile."""

    column: SealedColumn
    resealed: int = 0
    current: int = 0
    unopened: int = 0
    # Rows somebody wrote between the read and the write: left as they are, for the next pass.
    moved: int = 0

    @property
    def is_done(self) -> bool:
        """Whether every value of the column is under the newest key: the old key may be taken out."""
        return self.unopened == 0 and self.moved == 0


# Nothing is sealed again that no key opens: that row is counted, and the old key stays listed until
# the count is 0. A row written while the pass ran is counted too, and the pass is run again: until
# 2026-11 it was counted nowhere, the pass said it was clean, and the operator took out a key rows
# were still sealed under. The newest key must be first everywhere (the gateway restarted on the new
# list) before the old one is taken out.
async def reseal_everything(sessions: async_sessionmaker[AsyncSession], vault: Vault) -> list[Resealed]:
    """Seal every sealed value of the schema under the vault's newest key, and count each column."""
    return [await _reseal_column(sessions, vault, column) for column in list_sealed_columns()]


async def _reseal_column(sessions: async_sessionmaker[AsyncSession], vault: Vault, column: SealedColumn) -> Resealed:
    counted = {"resealed": 0, "current": 0, "unopened": 0, "moved": 0}
    after, more = THE_START, True
    while more:
        async with sessions() as session:
            values = await SealedRepository(session).list_values(column, after=after, page=A_PAGE_OF_VALUES)
        for value in values:
            counted[await _reseal_value(sessions, vault, column, value)] += 1
        more = len(values) == A_PAGE_OF_VALUES
        if values:
            after = values[-1].row
    return Resealed(column, **counted)


# One transaction a row: a pass cut short has sealed whole values.
async def _reseal_value(
    sessions: async_sessionmaker[AsyncSession], vault: Vault, column: SealedColumn, value: SealedValue
) -> str:
    if vault.is_under_newest(value.token):
        return "current"
    try:
        new = vault.reseal(value.token)
    except ServiceUnavailable:
        return "unopened"
    async with sessions.begin() as session:
        return "resealed" if await SealedRepository(session).reseal(column, value, new) else "moved"
