"""The SQLAlchemy base every model declares on, the naming, the column types, and what a table keeps and for whom."""

from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, ClassVar, override

from pgvector.sqlalchemy import HALFVEC
from sqlalchemy import TIMESTAMP, Dialect, MetaData, String, Text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.types import TypeDecorator

# Constraint names as the live schema has them: `<table>_pkey`, `<table>_<col>_key`.
NAMING = MetaData(
    naming_convention={
        "ix": "ix_%(column_0_N_label)s",
        "uq": "%(table_name)s_%(column_0_N_name)s_key",
        "ck": "%(table_name)s_%(constraint_name)s_check",
        "fk": "%(table_name)s_%(column_0_N_name)s_fkey",
        "pk": "%(table_name)s_pkey",
    }
)

VECTOR_WIDTH = 1024


def utc_now() -> datetime:
    """Now, timezone-aware."""
    return datetime.now(UTC)


# What a table is to whoever must forget, hand over or re-seal what the box keeps. Each model says it of
# itself, in the one file its author opens; nothing else names the table, so a new table cannot be left out:
# a test fails on a model that says nothing. A row goes with its org by the foreign key's cascade; what goes
# with one call, one agent or one contact is found by the column named here.
@dataclass(frozen=True, slots=True)
class Kept:
    """What a table keeps: the columns that name whose a row is, what an export carries, and why a row stays."""

    # The column that names the call a row came from (`call`, `source_call`, `log`), the agent, the contact.
    call: str | None = None
    agent: str | None = None
    contact: str | None = None
    # The columns an org's export carries; none, and `not_exported` says why.
    exported: tuple[str, ...] = ()
    not_exported: str = ""
    # Why an erasure leaves the row, for a table that names an org, a call, an agent or a contact and stays.
    outlives: str = ""


class Model(DeclarativeBase):
    """Base of every table."""

    __abstract__ = True
    metadata = NAMING
    __kept__: ClassVar[Kept]

    type_annotation_map = {
        dict[str, Any]: JSONB,
        list[str]: ARRAY(String),
        datetime: TIMESTAMP(timezone=True),
    }


class StringEnum[E: StrEnum](TypeDecorator[E]):
    """An enum kept as its text, so the column reads as the database wrote it."""

    impl = Text
    cache_ok = True

    def __init__(self, enum: type[E]) -> None:
        super().__init__()
        self.enum = enum

    # The enum's text is taken too, checked against the enum: a wrong word fails here, naming it,
    # not inside the driver as an attribute error.
    @override
    def process_bind_param(self, value: E | str | None, dialect: Dialect) -> str | None:
        """The enum's value to the column; its text is read as the enum first."""
        return None if value is None else str(self.enum(value).value)

    @override
    def process_result_value(self, value: str | None, dialect: Dialect) -> E | None:
        """The column's text to the enum."""
        return None if value is None else self.enum(value)


# The same text column to the database (`alembic check` sees no change); the type is the declaration.
class Sealed(TypeDecorator[str]):
    """A column the vault seals: its text is ciphertext, re-sealed when the vault's key is rotated."""

    impl = Text
    cache_ok = True


class Vector(HALFVEC):
    """A halfvec(1024): every embedding the box keeps is this wide."""

    def __init__(self) -> None:
        super().__init__(VECTOR_WIDTH)
