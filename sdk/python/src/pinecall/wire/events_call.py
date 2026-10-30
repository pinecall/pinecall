"""A call's life as its log tells it: ringing to summary, a confirm, a supervisor."""

from typing import Literal

from pydantic import Field

from pinecall.wire._names import Channel, Direction, Env, JsonObject, Medium
from pinecall.wire.frames import WireModel
from pinecall.wire.metrics import (
    ModelUsage,
)
from pinecall.wire.parts import Contact, Cost, EndedBy, EndReason, Route, Supervisor, TransferMode


class AttentionAnswered(WireModel):
    """An ask for a person settled: a supervisor took the line, or the wait ran out."""

    ok: bool
    by: Supervisor | None
    error: str | None = None


class AttentionRequested(WireModel):
    """The agent asked for a person: the caller is on hold until a supervisor takes the line."""

    reason: str
    wait_s: float


class CallStarted(WireModel):
    """Media is up: the caller and the agent can hear each other, or the text session is open."""

    channel: Channel
    direction: Direction
    from_: str = Field(alias="from")
    to: str
    run: str | None = None
    persona: str | None = None
    # What the simulated caller expects of the agent, one demand a line; its judge reads them.
    expects: list[str] | None = None
    caller: Contact | None
    started_at: float
    env: Env | None = None
    worker: str | None = None
    medium: Medium | None = None
    state: JsonObject | None = None
    # The day the call runs in, on a call an eval run opened: a golden may pin it.
    today: str | None = None
    # What the call was opened with and sealed: the token's `metadata`, as sent.
    metadata: JsonObject | None = None


class CallAttached(WireModel):
    """A call changed hands without ending."""

    app: str
    started: CallStarted
    state: JsonObject
    seq: int
    claimed: str | None = None


class CallClaimed(WireModel):
    """The call was bound to a page's code."""

    code: str
    via: Literal["keypad", "agent"]


class CallDialing(WireModel):
    """The platform is placing an outbound call and the far end has not answered yet."""

    channel: Channel
    from_: str = Field(alias="from")
    to: str
    run: str | None = None
    caller: Contact | None
    external_id: str | None = None
    asked_by: str | None = None


class CallEnded(WireModel):
    """The call is over; call.summary still follows."""

    reason: EndReason
    ended_by: EndedBy
    ended_at: float
    duration_s: float


class CallLine(WireModel):
    """The line's hold and mute flags after one of them changed."""

    held: bool
    muted: bool


class CallRinging(WireModel):
    """An inbound call is offered to this agent and has not been answered yet."""

    channel: Channel
    from_: str = Field(alias="from")
    to: str
    route: Route
    run: str | None = None
    caller: Contact | None
    external_id: str | None = None


class CallSummary(WireModel):
    """What the call was about, how it went, what it consumed and what that cost."""

    reason: EndReason
    outcome: str
    duration_s: float
    turns: int
    usage: list[ModelUsage]
    cost: Cost
    recording: str | None = None
    # A simulated caller played the other end: billed as one simulation, not minutes.
    simulated: bool = False
    # The eval run that opened the call: its minutes are the run's, never the org's.
    run: str | None = None


class CallTransferred(WireModel):
    """A transfer asked for by the agent or a supervisor finished, one way or the other."""

    to: str
    mode: TransferMode | None = None
    ok: bool
    error: str | None = None


class ConfirmDeclined(WireModel):
    """The caller did not say yes, or the request lapsed; the tool does not run."""

    tool: str
    call_id: str
    audience: str
    said: str | None = None
    reason: Literal["no", "timeout", "changed", "cancelled"]


class ConfirmGranted(WireModel):
    """The caller said yes; the token minted for it never enters the log."""

    tool: str
    call_id: str
    audience: str
    said: str
    ttl_s: int


class ConfirmRequest(WireModel):
    """A tool with confirm set is about to run and the platform is asking the caller."""

    tool: str
    call_id: str
    arguments: JsonObject
    audience: str
    phrase: str
    ttl_s: int


class SupervisorEnded(WireModel):
    """A supervisor hung up the call."""

    by: Supervisor
    reason: str | None = None


class SupervisorReleased(WireModel):
    """The supervisor gave the line back; the agent resumes with the history intact."""

    by: Supervisor


class SupervisorSaid(WireModel):
    """A supervisor made the agent say this to the caller."""

    by: Supervisor
    text: str


class SupervisorTookOver(WireModel):
    """A supervisor took the line; the agent is quiet until supervisor.released."""

    by: Supervisor


class SupervisorTransferred(WireModel):
    """A supervisor asked for a transfer."""

    by: Supervisor
    to: str
    mode: TransferMode | None = None


class SupervisorWhispered(WireModel):
    """A supervisor told the agent something the caller never heard."""

    by: Supervisor
    text: str
