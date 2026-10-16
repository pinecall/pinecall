"""The base of every wire model, and its frames: an entry, a command, a batch's entry."""

import time
from typing import Any, Self

from pydantic import BaseModel, ConfigDict
from pydantic import ValidationError as PydanticValidationError

from pinecall_runtime.exceptions import ValidationError


class WireModel(BaseModel):
    """A shape on the wire: unknown keys refused; a field builds by name or alias."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    @classmethod
    def parse(cls, raw: Any, what: str) -> Self:
        """Build from decoded JSON, raising ValidationError with what did not fit."""
        try:
            return cls.model_validate(raw)
        except PydanticValidationError as error:
            raise ValidationError(f"{what}: {error}") from error

    @classmethod
    def parse_json(cls, raw: str | bytes, what: str) -> Self:
        """Build from JSON text in pydantic's own parser, raising ValidationError."""
        try:
            return cls.model_validate_json(raw)
        except PydanticValidationError as error:
            raise ValidationError(f"{what}: {error}") from error

    def dump(self) -> dict[str, Any]:
        """As it goes on the wire: wire keys, absent fields absent, JSON values."""
        return self.model_dump(mode="json", by_alias=True, exclude_unset=True)

    def dump_json(self) -> str:
        """As `dump()`, as JSON text in one step."""
        return self.model_dump_json(by_alias=True, exclude_unset=True)


class Entry(WireModel):
    """One line of a call's log, or of an agent's log when call is null; seq is the order."""

    seq: int
    ts: float
    call: str | None
    agent: str
    type: str
    ephemeral: bool
    data: dict[str, Any]

    # Sent down an app's socket and never stored: no call, no seq.
    @classmethod
    def unstored(cls, agent: str, kind: str, data: dict[str, Any]) -> Self:
        """An entry of the agent's that no log keeps."""
        return cls(seq=0, ts=time.time(), call=None, agent=agent, type=kind, ephemeral=True, data=data)


class Command(WireModel):
    """One instruction from an app to the gateway over its WebSocket."""

    type: str
    agent: str
    call: str | None
    id: str | None = None
    data: dict[str, Any]


# `ts` is the worker's clock when the event happened; the gateway never stamps it past its own.
class BatchedEntry(WireModel):
    """One entry of a worker's batch: what it is, whether a store keeps it, and when it happened."""

    type: str
    data: dict[str, Any]
    ephemeral: bool | None = None
    ts: float
