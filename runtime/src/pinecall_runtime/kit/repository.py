"""The repository base: a model's queries on a session, one subclass per aggregate."""

from collections.abc import AsyncGenerator, Sequence
from typing import Any, Self

from sqlalchemy import CursorResult, Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.base import ExecutableOption
from sqlalchemy.sql.dml import UpdateBase

from pinecall_runtime.kit.db import Model

type Options = Sequence[ExecutableOption]


class Repository[M: Model]:
    """Every query on one model, run on the session the repository was given."""

    model: type[M]

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    @classmethod
    def of(cls, session: AsyncSession) -> Self:
        """The repository on this session."""
        return cls(session)

    def statement(self) -> Select[M]:
        """`select(model)`: what every query of the repository starts from."""
        return select(self.model)

    async def one(self, statement: Select[M]) -> M:
        """Exactly one row; raises when there is none or more than one."""
        result = await self.session.execute(statement)
        return result.unique().scalar_one()

    async def one_or_none(self, statement: Select[M]) -> M | None:
        """One row, or None."""
        result = await self.session.execute(statement)
        return result.unique().scalar_one_or_none()

    async def all(self, statement: Select[M]) -> Sequence[M]:
        """Every row the statement selects."""
        result = await self.session.execute(statement)
        return result.scalars().unique().all()

    async def stream(self, statement: Select[M], *, batch: int = 500) -> AsyncGenerator[M]:
        """The rows one by one without holding them all; for a statement with no collection join."""
        result = await self.session.stream_scalars(statement, execution_options={"yield_per": batch})
        try:
            async for row in result:
                yield row
        finally:
            await result.close()

    async def count(self, statement: Select[M]) -> int:
        """How many rows the statement selects."""
        counted = statement.with_only_columns(func.count()).order_by(None)
        return (await self.session.execute(counted)).scalar_one()

    async def exists(self, statement: Select[M]) -> bool:
        """Whether the statement selects any row."""
        return await self.one_or_none(statement.limit(1)) is not None

    # The async session's `execute` is typed as any Result; a DML statement's is the cursor's, which
    # counts the rows it touched.
    async def changed(self, statement: UpdateBase) -> int:
        """Run the update or delete; how many rows it touched."""
        result = await self.session.execute(statement)
        return result.rowcount if isinstance(result, CursorResult) else 0

    async def add(self, row: M, *, flush: bool = True) -> M:
        """Insert the row; flushed at once unless told otherwise, so its defaults are read back."""
        self.session.add(row)
        if flush:
            await self.session.flush()
        return row

    async def add_all(self, rows: Sequence[M]) -> Sequence[M]:
        """Insert the rows in one flush."""
        self.session.add_all(rows)
        await self.session.flush()
        return rows

    async def update(self, row: M, **values: Any) -> M:
        """Set the values on the row and flush."""
        for name, value in values.items():
            setattr(row, name, value)
        await self.session.flush()
        return row

    async def delete(self, row: M) -> None:
        """Delete the row and flush."""
        await self.session.delete(row)
        await self.session.flush()
