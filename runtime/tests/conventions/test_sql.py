"""Every raw statement prepares on the test database, and a parameter Postgres reads as JSON is typed as one."""

import importlib
import pkgutil
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncEngine
from sqlalchemy.sql.elements import TextClause
from sqlalchemy.types import JSON

import pinecall_runtime
from tests.conftest import needs_the_database

# What asyncpg encodes from a str alone: a Python value bound to one must be typed, so SQLAlchemy serializes it.
JSON_TYPES = frozenset({"json", "jsonb"})


@dataclass(frozen=True)
class Statement:
    """A `text()` the runtime keeps at module level, and where."""

    name: str
    clause: TextClause


def statements() -> list[Statement]:
    """Every module-level `text()` of the package, the migrations' env left out."""
    found: list[Statement] = []
    for info in pkgutil.walk_packages(pinecall_runtime.__path__, "pinecall_runtime."):
        if ".migrations" in info.name or info.name.endswith("__main__"):
            continue
        module = importlib.import_module(info.name)
        for attribute, value in vars(module).items():
            if isinstance(value, TextClause):
                found.append(Statement(f"{info.name}.{attribute}", value))
    return found


# A bind written `:name::text` is not one: psycopg's `%s::text` ported by hand reaches Postgres as a bare
# `:`. Preparing finds that, every typo, and every table or column the statement names and the schema lacks.
@needs_the_database
async def test_every_raw_statement_prepares_and_types_its_json(engine: AsyncEngine) -> None:
    """Postgres parses and plans each statement; a parameter it infers as JSON carries a JSON type."""
    wrong: list[str] = []
    async with engine.connect() as connection:
        driver = (await connection.get_raw_connection()).driver_connection
        assert driver is not None, "the pooled connection carries no asyncpg connection"
        for statement in statements():
            compiled = statement.clause.compile(dialect=engine.dialect)
            try:
                prepared = await driver.prepare(str(compiled))
            except Exception as refused:  # whatever Postgres said, reported beside the statement
                wrong.append(f"{statement.name}: {refused}")
                continue
            inferred = prepared.get_parameters()
            for position, name in enumerate(compiled.positiontup or ()):
                if inferred[position].name in JSON_TYPES and not isinstance(compiled.binds[name].type, JSON):
                    wrong.append(f"{statement.name}: :{name} is {inferred[position].name} to Postgres, untyped here")
    assert not wrong, "\n".join(wrong)
