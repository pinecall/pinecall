"""The flows endpoints' bodies and answers: an event sent, the work an app is owed, a run and its steps."""

from datetime import datetime
from typing import Any, Literal

from pydantic import Field, field_validator, model_validator

from runtime.enums import RunStatus, StepKind
from runtime.kit.schemas import Row
from runtime.kit.text import Json, JsonObject, a_mapping
from runtime.wire.base import WireModel
from runtime.wire.flows import StepSent, fit


class EventRequest(WireModel):
    """POST /v1/apps/{app}/events: an event for the app's own handlers."""

    name: str = Field(min_length=1, max_length=120)
    data: JsonObject = Field(default_factory=dict[str, Json])

    _fits = field_validator("data")(fit)


class EventRow(Row):
    """An event as the app's process is handed it."""

    id: int
    name: str
    data: JsonObject
    sent_at: datetime


class EventSent(Row):
    """An event kept: its id."""

    id: int


class StepRow(Row):
    """One step of a run's journal; `result` is absent while the step is not over."""

    seq: int
    kind: StepKind
    asked: JsonObject
    over: bool
    result: Json = None

    # The journal keeps `{"value": …}` once a step is over and nothing while it is open, so that a step
    # that came to nothing is not one still open: the two are told apart here, and the value unwrapped.
    # A row already read (a body validated again) is left as it is.
    @model_validator(mode="before")
    @classmethod
    def _read_what_it_came_to(cls, step: Any) -> Any:
        if a_mapping(step):
            return step
        kept = step.result
        value = None if kept is None else kept.get("value")
        return {"seq": step.seq, "kind": step.kind, "asked": step.asked, "over": kept is not None, "result": value}


class RunRow(Row):
    """A run, with its journal when it is handed out as work or read by its id."""

    id: str
    flow: str
    input: JsonObject
    status: RunStatus
    wake_at: datetime | None = None
    waits_for: str | None = None
    call: str | None = None
    error: str | None = None
    started_at: datetime
    moved_at: datetime
    steps: list[StepRow] = Field(default_factory=list[StepRow])

    # Answered alone, a run is its row and its journal is left out; handed out as work or read by its id
    # it comes as the run and its steps beside it (`service.RunWithSteps`), read here as one row.
    @model_validator(mode="before")
    @classmethod
    def _read_beside_its_steps(cls, given: Any) -> Any:
        run = getattr(given, "run", None)
        if run is None:
            return given
        row = {name: getattr(run, name) for name in cls.model_fields if name != "steps"}
        return {**row, "steps": list(given.steps)}


class RunList(Row):
    """The app's runs, newest first."""

    runs: list[RunRow]


class StartRequest(WireModel):
    """POST /v1/apps/{app}/runs: a flow started with an input; the same key starts it once."""

    flow: str = Field(min_length=1, max_length=120)
    key: str = Field(min_length=1, max_length=200)
    input: JsonObject = Field(default_factory=dict[str, Json])

    _fits = field_validator("input")(fit)


class WorkRequest(WireModel):
    """POST /v1/apps/{app}/work: what the app's process is owed, waited for up to `wait_s`."""

    wait_s: float = Field(default=0.0, ge=0, le=25)


class Work(Row):
    """The events the app has not heard and the runs ready to go on, each held for this process."""

    events: list[EventRow]
    runs: list[RunRow]


# `sleep` asks `{until}` (an ISO time); `wait` asks `{event, match?, until?}`; `call` asks `{agent, to, …}`
# as a dial does; `run` and `emit` are over as they are written, and `run` carries its `result`. What
# each asks is a shape of `wire/flows.py`, read once the journal says the step is its next.
class StepRequest(StepSent):
    """POST /v1/apps/{app}/runs/{run}/steps: the next step of the run's journal."""


class EndRequest(WireModel):
    """POST /v1/apps/{app}/runs/{run}/end: the flow returned, or threw."""

    status: Literal["done", "failed"]
    error: str | None = Field(default=None, max_length=2000)
