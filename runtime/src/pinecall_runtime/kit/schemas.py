"""The pydantic bases: what a body is read as, and how a row is answered."""

from typing import Any, Self

from pydantic import BaseModel, ConfigDict
from pydantic import ValidationError as PydanticValidationError

from pinecall_runtime.exceptions import ValidationError


class Schema(BaseModel):
    """A request body: unknown keys refused, built by name or alias."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True, str_strip_whitespace=True)

    @classmethod
    def read(cls, raw: Any, what: str) -> Self:
        """Build from decoded JSON, raising ValidationError with what did not fit."""
        try:
            return cls.model_validate(raw)
        except PydanticValidationError as error:
            raise ValidationError(f"{what}: {error}") from error

    def dump(self) -> dict[str, Any]:
        """As JSON values, by alias, absent fields absent."""
        return self.model_dump(mode="json", by_alias=True, exclude_unset=True)


class Row(BaseModel):
    """A response body built from a model (or anything with the attributes), by alias."""

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    @classmethod
    def of(cls, row: Any, /) -> Self:
        """The body the row answers as."""
        return cls.model_validate(row)


class Page[T](BaseModel):
    """A page of rows and the cursor to ask for the next; None when this is the last."""

    items: list[T]
    next: int | None = None


DEFAULT_LIMIT = 200
MAX_LIMIT = 1000
