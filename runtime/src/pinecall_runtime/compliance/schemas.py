"""The bodies of the policy, reads and telemetry endpoints."""

from typing import Annotated, Self

from pydantic import Field, model_validator

from pinecall_runtime.enums import Env, ReadKind
from pinecall_runtime.kit.schemas import Row, Schema


class CallingHours(Schema):
    """The hours of the called number's own day a call may ring: from, until (exclusive)."""

    from_: Annotated[int, Field(ge=0, le=23)] = Field(alias="from")
    until: Annotated[int, Field(ge=1, le=24)]

    @model_validator(mode="after")
    def _a_window(self) -> Self:
        if self.from_ >= self.until:
            raise ValueError(f"calling hours from {self.from_} until {self.until} leave no hour")
        return self


class OrgPolicy(Schema):
    """GET and PUT /v1/org/policy: the org's compliance settings, replaced whole."""

    retention_days: Annotated[int, Field(gt=0)] | None = None
    calling_hours: CallingHours | None = None
    per_number_day: Annotated[int, Field(gt=0)] | None = None
    consent_everywhere: bool = False
    # An outbound call's opening sentence: null is the platform's, "" is none.
    disclosure: Annotated[str, Field(max_length=500)] | None = None
    recording_notice: bool = True


class OrgPolicyRow(Row):
    """GET /v1/org/policy: the settings, who set them last, and when."""

    policy: OrgPolicy
    set_by: str | None
    set_at: float | None


class ReadRow(Row):
    """One read of the org's data: the call or number, what of it, who, and when."""

    subject: str
    what: ReadKind
    env: Env | None
    # A person's id, or "operator" for the box's operator.
    reader: str
    at: float


class ReadsResponse(Row):
    """GET /v1/org/reads: who read the org's calls, newest first."""

    reads: list[ReadRow]


class TelemetryRequest(Schema):
    """PUT /v1/telemetry: the collector, its headers (a credential, never read back), and PII."""

    endpoint: str
    headers: dict[str, str] = Field(default_factory=dict[str, str])
    pii: bool = False


class TelemetryResponse(Row):
    """GET /v1/telemetry: the collector and which headers are set; null when traces go nowhere."""

    endpoint: str
    header_names: list[str]
    pii: bool
