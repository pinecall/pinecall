"""The bodies of the compliance endpoints: the policy, the reads, consent and the do-not-call list, the dial guards."""

from typing import Annotated, Any, Literal, Self, override

from pydantic import Field, model_validator

from runtime.enums import ConsentKind, Env, ReadKind
from runtime.kit.schemas import Epoch, Row, Schema

# ── the policy ──


class CallingHours(Schema):
    """The hours of the called number's own day a call may ring: from, until (exclusive)."""

    from_: Annotated[int, Field(ge=0, le=23)] = Field(alias="from")
    until: Annotated[int, Field(ge=1, le=24)]

    @model_validator(mode="after")
    def _a_window(self) -> Self:
        if self.from_ >= self.until:
            raise ValueError(f"calling hours from {self.from_} until {self.until} leave no hour")
        return self


class PolicyBody(Schema):
    """PUT /v1/org/policy: the org's compliance settings, replaced whole."""

    retention_days: Annotated[int, Field(gt=0)] | None = None
    calling_hours: CallingHours | None = None
    per_number_day: Annotated[int, Field(gt=0)] | None = None
    consent_everywhere: bool = False
    # An outbound call's opening sentence: null is the platform's, "" is none.
    disclosure: Annotated[str, Field(max_length=500)] | None = None
    recording_notice: bool = True


class PolicyRow(Row):
    """GET /v1/org/policy: the settings, who set them last, and when."""

    policy: PolicyBody
    set_by: str | None
    set_at: Epoch | None

    # The policy is one flat value; the answer nests its settings, as the PUT's body is written.
    @classmethod
    @override
    def of(cls, row: Any, /) -> Self:
        """The answer a policy reads as: its settings, then who set them and when."""
        settings = PolicyBody.model_validate(row, from_attributes=True)
        return cls(policy=settings, set_by=row.set_by, set_at=row.set_at)


# ── who read what ──


class ReadRow(Row):
    """One read of the org's data: the call or number, what of it, who, and when."""

    subject: str
    what: ReadKind
    env: Env | None
    # A person's id, or "operator" for the box's operator.
    reader: str
    at: Epoch


class ReadsResponse(Row):
    """GET /v1/org/reads: who read the org's calls, newest first."""

    reads: list[ReadRow]


# ── consent and the do-not-call list ──


class RecordConsent(Schema):
    """POST /v1/org/consents: one fact about a number, a consent given or an opt-out."""

    number: str
    kind: ConsentKind
    source: str = Field(min_length=1, max_length=200)
    text: str | None = Field(default=None, max_length=2000)
    evidence: str | None = Field(default=None, max_length=500)


class ConsentRow(Row):
    """One fact about a number: a consent or an opt-out, by whom, from what, on which call."""

    kind: ConsentKind
    source: str
    text: str | None
    evidence: str | None
    given_by: str
    call: str | None
    given_at: Epoch


class ConsentHistory(Row):
    """GET /v1/org/consents/{number}: what stands for the number, and every row, newest first."""

    number: str
    standing: Literal["consented", "opted_out", "unknown"]
    rows: list[ConsentRow]


class OptedOut(Row):
    """A number on the org's do-not-call list: since when, from what, and who put it there."""

    number: str
    since: Epoch = Field(validation_alias="given_at")
    source: str
    given_by: str


class DoNotCall(Row):
    """GET /v1/org/dnc: the numbers whose newest row is an opt-out, newest first, a page."""

    numbers: list[OptedOut]
    next: str | None


class DoNotCallImport(Schema):
    """POST /v1/org/dnc: numbers the org's own list or a Registry scrub says not to call."""

    numbers: list[str] = Field(min_length=1, max_length=10000)
    source: str = Field(min_length=1, max_length=200)


class DoNotCallImported(Row):
    """POST /v1/org/dnc, the answer: how many numbers joined the list, and the ones refused."""

    added: int
    refused: list[str]


# ── the dial guards ──


class PutDialGuards(Schema):
    """PUT /v1/ops/orgs/{named}/dialling: the guards whole; one left out is the default."""

    dial_anywhere: bool | None = None
    per_minute: int | None = None
    per_day: int | None = None
    max_duration_s: int | None = None


class DialGuards(Row):
    """An org's dial guards: what it may dial and how often."""

    dial_anywhere: bool
    per_minute: int
    per_day: int
    max_duration_s: int
