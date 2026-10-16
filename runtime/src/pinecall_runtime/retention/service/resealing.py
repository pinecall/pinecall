"""The vault key rotated: every sealed value of every domain's table sealed again under the newest key."""

from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from pinecall_runtime.exceptions import ServiceUnavailable
from pinecall_runtime.kit.crypto import Vault
from pinecall_runtime.retention.repository.sealed import SEALED_COLUMNS, SealedColumn, SealedRepository


@dataclass(frozen=True, slots=True)
class Resealing:
    """One column after a pass: re-sealed now, already under the newest key, opened by no key."""

    column: SealedColumn
    resealed: int = 0
    current: int = 0
    unopened: int = 0


# Nothing is re-sealed that no key opens: that row is counted, and the old key stays listed until
# the count is 0. The newest key must be first everywhere (the gateway restarted on the new list)
# before the old one is taken out.
async def reseal_everything(sessions: async_sessionmaker[AsyncSession], vault: Vault) -> list[Resealing]:
    """Seal every sealed value of the schema under the vault's newest key, and count each column."""
    return [await _reseal_column(sessions, vault, column) for column in SEALED_COLUMNS]


async def _reseal_column(sessions: async_sessionmaker[AsyncSession], vault: Vault, column: SealedColumn) -> Resealing:
    async with sessions() as session:
        rows = await SealedRepository(session).tokens(column)
    resealed = current = unopened = 0
    for row, token in rows:
        if vault.is_under_newest(token):
            current += 1
            continue
        try:
            new = vault.reseal(token)
        except ServiceUnavailable:
            unopened += 1
            continue
        async with sessions.begin() as session:
            resealed += await SealedRepository(session).reseal(column, row, token, new)
    return Resealing(column, resealed=resealed, current=current, unopened=unopened)
