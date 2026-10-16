"""The SQLAlchemy base every model declares on, the naming convention, and the column types."""

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, override

from pgvector.sqlalchemy import HALFVEC
from sqlalchemy import TIMESTAMP, Dialect, MetaData, String, Text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
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


class Model(DeclarativeBase):
    """Base of every table."""

    __abstract__ = True
    metadata = NAMING

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

    @override
    def process_bind_param(self, value: E | None, dialect: Dialect) -> str | None:
        """The enum's value to the column."""
        return None if value is None else str(value.value)

    @override
    def process_result_value(self, value: str | None, dialect: Dialect) -> E | None:
        """The column's text to the enum."""
        return None if value is None else self.enum(value)


class Vector(HALFVEC):
    """A halfvec(1024): every embedding the box keeps is this wide."""

    def __init__(self) -> None:
        super().__init__(VECTOR_WIDTH)


def set_at_column() -> Mapped[datetime]:
    """The `set_at timestamptz NOT NULL DEFAULT now()` most settings rows carry."""
    return mapped_column(TIMESTAMP(timezone=True), nullable=False, default=utc_now)
