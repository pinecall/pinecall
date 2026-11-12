"""The pydantic bases: what a body is read as, and how a row is answered."""

from datetime import datetime
from typing import Annotated, Any, Self

from pydantic import AfterValidator, BaseModel, ConfigDict, PlainSerializer
from pydantic import ValidationError as PydanticValidationError

from runtime.exceptions import ValidationError
from runtime.kit.text import parse_email

# An address is read once, where it enters: trimmed, lowercased, refused when it is not one. Nothing
# below a body parses an address again, so the same person is never two spellings of one address.
EmailAddress = Annotated[str, AfterValidator(parse_email)]


def _epoch_of(moment: datetime) -> float:
    return moment.timestamp()


# A moment the wire carries as seconds since the epoch: the field is declared `at: Epoch`, read off the
# row as the datetime it is, and answered as a float. One type where each body had its own serializer.
Epoch = Annotated[datetime, PlainSerializer(_epoch_of, return_type=float)]


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

    # Asked at the call, attributes are read at every depth: the class's own setting reads the row's
    # and leaves a nested shape of the wire, which sets none, refusing whatever is not its own class.
    # Until 2026-11-12 an agent with a greeting answered 500 at GET /v1/agents/{slug}/pipeline.
    @classmethod
    def of(cls, row: Any, /) -> Self:
        """The body the row answers as."""
        return cls.model_validate(row, from_attributes=True)
