"""A golden on the wire: the turns it plays, what must follow each, and what holds at the end."""

from datetime import date
from typing import Literal, Self

from pydantic import Field, model_validator

from pinecall_runtime.kit.text import Json, JsonObject
from pinecall_runtime.wire.base import WireModel
from pinecall_runtime.wire.parts import EndedBy

# How a Spanish-speaking agent addresses the caller.
type Register = Literal["tu", "usted"]

# Each turn is one the box pays the agent's model for.
MOST_TURNS = 40


class InjectedEvent(WireModel):
    """A fact of the tenant's backend, sent as the app's own `call.event` at its turn."""

    name: str
    data: JsonObject = Field(default_factory=dict[str, Json])


class ToolStep(WireModel):
    """The next tool call of the turn is this one, with these arguments among its own."""

    tool: str
    # A subset: every key named must be there with this value; others may be too.
    args: JsonObject | None = None
    # From the turn's input to the tool call.
    within_ms: int | None = Field(default=None, gt=0)


class NoToolStep(WireModel):
    """No call of this tool anywhere in the turn."""

    no_tool: str


class Reply(WireModel):
    """What the agent's next turn says: phrases by code, an intent by the judge model."""

    says: list[str] = Field(default_factory=list[str])
    # Any one of these is enough: a reply with several right wordings.
    says_any: list[str] = Field(default_factory=list[str])
    not_said: list[str] = Field(default_factory=list[str], alias="not")
    # One sentence the judge model holds that turn to; the only part a model answers.
    intent: str | None = Field(default=None, min_length=1)
    # From the turn's input to the agent's turn.
    within_ms: int | None = Field(default=None, gt=0)


class ReplyStep(WireModel):
    """The agent's next turn, and what it must say."""

    reply: Reply


class EndStep(WireModel):
    """The call ended in this turn, by this side."""

    end: EndedBy


class NothingElseStep(WireModel):
    """After the step before it, the turn holds no other tool call and no other agent turn."""

    nothing_else: Literal[True]


# Each step names itself by its one required key, so a step reads as exactly one of these.
type Step = ToolStep | NoToolStep | ReplyStep | EndStep | NothingElseStep


class Turn(WireModel):
    """One input, a caller's line or a backend's fact; after a line, what must follow, in order."""

    say: str | None = Field(default=None, min_length=1)
    event: InjectedEvent | None = None
    then: list[Step] = Field(default_factory=list[Step])

    @model_validator(mode="after")
    def _one_input(self) -> Self:
        if (self.say is None) == (self.event is None):
            raise ValueError("a turn says a line or sends an event: exactly one of say and event")
        # A line is run as livekit's test run, whose events the steps read; a fact is not a run.
        if self.event is not None and self.then:
            raise ValueError(
                "an event's turn takes no then: what the agent does with the fact is judged in the next line's turn"
            )
        return self


class Expect(WireModel):
    """What holds over the whole conversation; each field set is one check."""

    tools: list[str] = Field(default_factory=list[str])
    not_tools: list[str] = Field(default_factory=list[str])
    not_said: list[str] = Field(default_factory=list[str], alias="not")
    says: list[str] = Field(default_factory=list[str])
    says_any: list[str] = Field(default_factory=list[str])
    # Every price, hour, date and name the agent stated is in the call's evidence.
    grounded: bool = False
    # A field named `register` would shadow a pydantic attribute.
    addressed_as: Register | None = Field(default=None, alias="register")
    # Judges asked of the golden's call by name: the library's, the org's or the agent's own.
    judges: list[str] = Field(default_factory=list[str])


class Golden(WireModel):
    """One scripted conversation: the state it opens in, its turns, and what holds at the end."""

    name: str
    state: JsonObject = Field(default_factory=dict[str, Json])
    turns: list[Turn] = Field(default_factory=list[Turn], max_length=MOST_TURNS)
    # Answered to `recall` for this call only; the memory table is never written.
    memory: list[str] = Field(default_factory=list[str])
    # The day the model is told it is; the real one when absent.
    today: date | None = None
    expect: Expect = Field(default_factory=Expect)
    # The call `pinecall runs promote` made it from; no judge reads it.
    promoted_from: str | None = None
