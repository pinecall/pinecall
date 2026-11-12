"""A flow's steps as an app's process sends them: the step as it arrives, and what each kind asks, read."""

import json
from typing import Annotated

from pydantic import AfterValidator, AwareDatetime, BeforeValidator, ConfigDict, Field, field_validator

from runtime.enums import StepKind
from runtime.kit.text import Json, JsonObject
from runtime.wire.base import WireModel

# What an event, a run's input or a step may carry: an id and a few facts, never a document.
MOST_BYTES = 16384

A_SLEEP_ASKS = "a sleep step asks {until}: a time, ISO 8601 with its zone: 2026-11-12T09:30:00-08:00"
A_WAIT_ASKS = "a wait step asks {event, match?, until?}: the event's name, what of its data must match, and a time"
A_CALL_ASKS = "a call step asks {agent, to}: the agent that calls, and the number in +E.164"
AN_EMIT_ASKS = "an emit step asks {name, data?}: the event's name, and what it carries"


def fit(given: JsonObject) -> JsonObject:
    """The object, when it is small enough to be kept in a journal or handed to a process."""
    if len(json.dumps(given)) > MOST_BYTES:
        raise ValueError(f"it carries {MOST_BYTES} bytes of JSON at most")
    return given


def _name(given: str) -> str:
    if not given.strip():
        raise ValueError("a name is not blank")
    return given


# A text that is not one, or is blank, was read as none said; an object left out or null as an empty one.
def _text_or_none(given: object) -> object:
    return given if isinstance(given, str) and given.strip() else None


def _object_or_empty(given: object) -> object:
    return given or {}


Name = Annotated[str, AfterValidator(_name)]
Words = Annotated[str | None, BeforeValidator(_text_or_none)]
Data = Annotated[JsonObject, BeforeValidator(_object_or_empty)]


# Until 2026-11 the service read what a step asks field by field, with a sentence of its own for each
# refusal, and a key it did not read was passed over: a call's opening is the tenant's own object,
# spread into what the step asks. So these read the same keys and pass over the rest.
class _Asked(WireModel):
    model_config = ConfigDict(extra="ignore", populate_by_name=True)


class SleepStep(_Asked):
    """`sleep` asks `{until}`: the time the run goes on at."""

    until: AwareDatetime


class WaitStep(_Asked):
    """`wait` asks `{event, match?, until?}`: an event of the app, what of its data must match, when to give up."""

    event: Name
    match: Data = Field(default_factory=dict[str, Json])
    until: AwareDatetime | None = None


class CallStep(_Asked):
    """`call` asks `{agent, to, …}` as a dial does: who calls, the number, and what the call opens with."""

    agent: str
    to: str
    from_: Words = Field(default=None, alias="from")
    state: Data = Field(default_factory=dict[str, Json])
    metadata: Data = Field(default_factory=dict[str, Json])
    greeting: Words = None
    instruction: Words = None


class EmitStep(_Asked):
    """`emit` asks `{name, data?}`: an event sent to the run's own app."""

    name: Name
    data: Data = Field(default_factory=dict[str, Json])


class RunStep(WireModel):
    """`run` asks nothing of the gateway: the process ran it, and `result` is what it came to."""

    result: Json = None


type Step = SleepStep | WaitStep | CallStep | RunStep | EmitStep


# What it asks is read after the journal was looked at (`flows.service.write_step`), never as the body
# arrives: a step sent again answers the one written, and one of another kind at its place is the
# refusal "the flow's code changed", whatever either asks.
class StepSent(WireModel):
    """The next step of a run's journal as its process sends it: its place, its kind, what it asks, its result."""

    seq: int = Field(ge=1, le=10000)
    kind: StepKind
    asked: JsonObject = Field(default_factory=dict[str, Json])
    result: Json = None

    _fits = field_validator("asked")(fit)

    def read(self) -> Step:
        """The step with what it asks read as its kind asks it; ValidationError where it does not fit."""
        match self.kind:
            case StepKind.sleep:
                return SleepStep.parse(self.asked, A_SLEEP_ASKS)
            case StepKind.wait:
                return WaitStep.parse(self.asked, A_WAIT_ASKS)
            case StepKind.call:
                return CallStep.parse(self.asked, A_CALL_ASKS)
            case StepKind.emit:
                return EmitStep.parse(self.asked, AN_EMIT_ASKS)
            case StepKind.run:
                return RunStep(result=self.result)
