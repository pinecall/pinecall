"""The bodies of the erasure endpoints: one erasure as its trail row says, and the org's trail."""

from datetime import datetime

from pydantic import field_serializer

from pinecall_runtime.enums import Env, ErasureKind
from pinecall_runtime.kit.schemas import Row


class ErasureRow(Row):
    """DELETE /v1/calls/{call}, /v1/contacts/{contact}: what one erasure took, as its trail says."""

    id: int
    at: datetime
    what: ErasureKind
    subject: str
    env: Env | None
    asked_by: str
    calls: int
    entries: int
    memories: int
    recordings: int

    @field_serializer("at")
    def _as_epoch(self, at: datetime) -> float:
        return at.timestamp()


class ErasureTrail(Row):
    """GET /v1/org/erasures: the org's erasures, newest first."""

    erasures: list[ErasureRow]
