"""What a dispatch tells the job it starts, as it rides a room's metadata between the processes."""

import json
from collections.abc import Mapping
from typing import Any

from pydantic import BaseModel, ConfigDict, Field
from pydantic import ValidationError as PydanticValidationError

from pinecall_runtime.enums import Direction, Env
from pinecall_runtime.kit.auth import Scope

# Whose sandbox copy a handed-over ring is for rides the leg's INVITE, a header each.
ORG_HEADER = "pinecall.org"
AGENT_HEADER = "pinecall.agent"
HOLDER_HEADER = "pinecall.holder"


class Dialling(BaseModel):
    """The leg an outbound job places: the trunk, the far end, the number shown, the ceiling."""

    model_config = ConfigDict(frozen=True, extra="ignore")

    trunk: str
    to: str
    shown: str
    max_duration_s: int = 0


# Written by the gateway alone, signed into a token or sent by the server API, so the worker
# trusts it. `extra="ignore"`: a room nobody dispatched reads as empty.
class Dispatch(BaseModel):
    """Whose call, which agent, and how it arrived."""

    model_config = ConfigDict(frozen=True, extra="ignore", populate_by_name=True)

    agent: str | None = None
    org: str | None = None
    env: Env | None = None
    holder: str | None = None
    direction: Direction = Direction.inbound
    caller: str | None = None
    contact: str | None = None
    scope: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict[str, Any])
    dial: Dialling | None = None
    app: str | None = None
    run: str | None = None
    persona: str | None = None
    expects: list[str] = Field(default_factory=list[str])
    diverted_from: Env | None = None
    state: dict[str, Any] = Field(default_factory=dict[str, Any])
    worker_gone: bool = False
    entries_written: int = 0
    continues: str | None = None

    def dump(self) -> str:
        """As a job's metadata: compact JSON, absent fields absent."""
        data = self.model_dump(mode="json", exclude_none=True, exclude_defaults=True)
        return json.dumps(data, separators=(",", ":"))

    @classmethod
    def parse(cls, metadata: str) -> "Dispatch":
        """The dispatch a job was started with; empty when there is none or it is somebody else's."""
        if not metadata:
            return cls()
        try:
            return cls.model_validate_json(metadata)
        except PydanticValidationError:
            return cls()

    @property
    def named_scope(self) -> Scope | None:
        """The scope the dispatch names, or None on the box's own trunk, where the number decides."""
        if self.org is None or self.env is None:
            return None
        return Scope(self.org, self.env, self.holder or "")

    def handed_in(self, attributes: Mapping[str, str]) -> "Dispatch":
        """The hand-over rule's dispatch made the developer's call, from what its leg carries."""
        if self.diverted_from is None or self.agent is not None or AGENT_HEADER not in attributes:
            return self
        return self.model_copy(
            update={
                "org": attributes.get(ORG_HEADER),
                "agent": attributes.get(AGENT_HEADER),
                "holder": attributes.get(HOLDER_HEADER),
            }
        )
