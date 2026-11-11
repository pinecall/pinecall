"""The flows endpoints' bodies and answers: an event sent, the work an app is owed, a run and its steps."""

import json
from datetime import datetime
from typing import Literal, cast

from pydantic import Field, field_validator

from pinecall_runtime.flows.models import AppEvent, FlowRun, FlowStep
from pinecall_runtime.kit.text import Json, JsonObject
from pinecall_runtime.wire.base import WireModel

# What an event, a run's input or a step may carry: an id and a few facts, never a document.
MOST_BYTES = 16384
StepKind = Literal["sleep", "call", "wait", "run", "emit"]


def _small(given: JsonObject) -> JsonObject:
    if len(json.dumps(given)) > MOST_BYTES:
        raise ValueError(f"it carries {MOST_BYTES} bytes of JSON at most")
    return given


class EventRequest(WireModel):
    """POST /v1/apps/{app}/events: an event for the app's own handlers."""

    name: str = Field(min_length=1, max_length=120)
    data: JsonObject = Field(default_factory=dict[str, Json])

    _fits = field_validator("data")(_small)


class EventRow(WireModel):
    """An event as the app's process is handed it."""

    id: int
    name: str
    data: JsonObject
    sent_at: datetime

    @classmethod
    def of(cls, event: AppEvent) -> "EventRow":
        """The row an event reads as."""
        return cls(id=event.id, name=event.name, data=event.data, sent_at=event.sent_at)


class EventSent(WireModel):
    """An event kept: its id."""

    id: int


class StepRow(WireModel):
    """One step of a run's journal; `result` is absent while the step is not over."""

    seq: int
    kind: StepKind
    asked: JsonObject
    over: bool
    result: Json = None

    @classmethod
    def of(cls, step: FlowStep) -> "StepRow":
        """The row a step reads as."""
        over = step.result is not None
        value = step.result.get("value") if step.result is not None else None
        return cls(seq=step.seq, kind=cast(StepKind, step.kind), asked=step.asked, over=over, result=value)


class RunRow(WireModel):
    """A run, with its journal when it is handed out as work."""

    id: str
    flow: str
    input: JsonObject
    status: str
    wake_at: datetime | None = None
    waits_for: str | None = None
    call: str | None = None
    error: str | None = None
    started_at: datetime
    moved_at: datetime
    steps: list[StepRow] = Field(default_factory=list[StepRow])

    @classmethod
    def of(cls, run: FlowRun, steps: list[FlowStep] | None = None) -> "RunRow":
        """The row a run reads as."""
        return cls(
            id=run.id,
            flow=run.flow,
            input=run.input,
            status=run.status,
            wake_at=run.wake_at,
            waits_for=run.waits_for,
            call=run.call,
            error=run.error,
            started_at=run.started_at,
            moved_at=run.moved_at,
            steps=[StepRow.of(step) for step in steps or ()],
        )


class RunList(WireModel):
    """The app's runs, newest first."""

    runs: list[RunRow]


class StartRequest(WireModel):
    """POST /v1/apps/{app}/runs: a flow started with an input; the same key starts it once."""

    flow: str = Field(min_length=1, max_length=120)
    key: str = Field(min_length=1, max_length=200)
    input: JsonObject = Field(default_factory=dict[str, Json])

    _fits = field_validator("input")(_small)


class WorkRequest(WireModel):
    """POST /v1/apps/{app}/work: what the app's process is owed, waited for up to `wait_s`."""

    wait_s: float = Field(default=0.0, ge=0, le=25)


class Work(WireModel):
    """The events the app has not heard and the runs ready to go on, each held for this process."""

    events: list[EventRow]
    runs: list[RunRow]


class StepRequest(WireModel):
    """POST /v1/apps/{app}/runs/{run}/steps: the next step of the run's journal.

    `sleep` asks `{until}` (an ISO time); `wait` asks `{event, match?, until?}`; `call` asks `{agent, to, …}`
    as a dial does; `run` and `emit` are over as they are written and carry their `result`.
    """

    seq: int = Field(ge=1, le=10000)
    kind: StepKind
    asked: JsonObject = Field(default_factory=dict[str, Json])
    result: Json = None

    _fits = field_validator("asked")(_small)


class EndRequest(WireModel):
    """POST /v1/apps/{app}/runs/{run}/end: the flow returned, or threw."""

    status: Literal["done", "failed"]
    error: str | None = Field(default=None, max_length=2000)
