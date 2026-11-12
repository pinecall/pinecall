"""The bodies of the erasure endpoints: one erasure as its trail row says, and the org's trail."""

from runtime.enums import Env, ErasureKind
from runtime.kit.schemas import Epoch, Row


class ErasureRow(Row):
    """DELETE /v1/calls/{call}, /v1/contacts/{contact}: what one erasure took, as its trail says."""

    id: int
    at: Epoch
    what: ErasureKind
    subject: str
    env: Env | None
    asked_by: str
    calls: int
    entries: int
    memories: int
    recordings: int


class ErasureTrail(Row):
    """GET /v1/org/erasures: the org's erasures, newest first."""

    erasures: list[ErasureRow]
