"""An org's env as JSON Lines: one line per row of every table that declares what it exports."""

from collections.abc import AsyncIterator

from sqlalchemy import Select, Table, Text, cast, func, literal, select

from runtime.enums import Env
from runtime.kit.db import Kept, list_kept
from runtime.kit.repository import Repository
from runtime.retention.models import Erasure

# The key every line says what it is under: a column of that name goes under another (`Kept.renamed`).
KIND = "kind"
# How many lines are read from the database at a time.
A_BATCH_OF_LINES = 500


# No table is named here: a model says which of its columns an export carries, the kind its lines say
# they are, and the key a column goes under where it is not its name (`Kept`). A line never carries
# the org or the env: the export's first line says both. Written by Postgres, so a value comes out as
# it is stored. A table whose owner writes its own lines (`Kept.exported_by`, a call with its log) is
# left to it.
class ExportRepository(Repository[Erasure]):
    """The org's rows in an env, table by table, each row already a JSON line."""

    model = Erasure

    async def stream_lines(self, org: str, env: Env) -> AsyncIterator[str]:
        """Every line of every table that declares an export, by table and then by the table's own key."""
        for table, kept in _list_exporting():
            lines = await self.session.stream_scalars(_lines_of(table, kept, org, env))
            async for batch in lines.partitions(A_BATCH_OF_LINES):
                for line in batch:
                    yield line


def _list_exporting() -> list[tuple[Table, Kept]]:
    return [
        (table, kept)
        for table, kept in list_kept()
        if kept.exported and not kept.exported_by and _find_owner_column(table) is not None
    ]


# A row is its org's by the `org` it names; the org's own row, the one every such column keys to, by its id.
def _find_owner_column(table: Table) -> str | None:
    if "org" in table.c:
        return "org"
    return "id" if table is _find_orgs_table() else None


def _find_orgs_table() -> Table | None:
    for table, _ in list_kept():
        column = table.c.get("org")
        for key in () if column is None else column.foreign_keys:
            return key.column.table
    return None


def _lines_of(table: Table, kept: Kept, org: str, env: Env) -> Select[str]:
    renamed = dict(kept.renamed)
    # A table's name is SQLAlchemy's own kind of string, which it binds with no type: said as text, or
    # Postgres cannot tell what the value of a JSON pair is.
    pairs: list[object] = [literal(KIND), literal(str(kept.exported_as or table.name), Text)]
    for column in kept.exported:
        pairs += [literal(renamed.get(column, column)), table.c[column]]
    owner = _find_owner_column(table)
    assert owner is not None
    statement = select(cast(func.jsonb_build_object(*pairs), Text)).where(table.c[owner] == org)
    if "env" in table.c:
        statement = statement.where(table.c.env == env)
    return statement.order_by(*table.primary_key.columns)
