"""A Studio agent's definition: the document the console writes and a release keeps."""

from typing import Annotated, Literal, Self

from pydantic import Field, model_validator

from runtime.wire.base import WireModel

type ParamType = Literal["string", "number", "integer", "boolean"]
type Method = Literal["GET", "POST", "PUT", "PATCH", "DELETE"]
# What a fixed field carries: a string (which may name the call's values), a number or a flag.
type Scalar = Annotated[str, Field(max_length=2000)] | int | float | bool

A_NAME = r"^[A-Za-z][A-Za-z0-9_]*$"
# A tool waits this long unless it says, and never longer than the ceiling: a turn is waiting.
TOOL_TIMEOUT_S = 10.0
LONGEST_TOOL_S = 30.0
# How long a tool runs before the agent says it is taking a while, unless the tool says: the framework's own.
DELAYED_AFTER_S = 5.0
MOST_TOOLS = 24
MOST_PARAMS = 16
MOST_FIELDS = 24
# A closed list of values past this is a lookup, not a parameter.
MOST_VALUES = 50
LONGEST_INSTRUCTIONS = 20_000
LONGEST_LINE = 300
LONGEST_CHANNEL_RULES = 2000


# Unknown keys are refused, as every wire shape refuses them: a misspelt field is said, never dropped.
class Header(WireModel):
    """One header a request carries; its value may name `{{secrets.NAME}}`."""

    name: str = Field(min_length=1, max_length=100, pattern=r"^[A-Za-z0-9-]+$")
    value: str = Field(max_length=2000)


class Param(WireModel):
    """One argument the model fills: a path's `{name}`, else the query of a GET or the JSON body."""

    name: str = Field(max_length=64, pattern=A_NAME)
    type: ParamType = "string"
    description: str = Field(default="", max_length=500)
    required: bool = True
    # The values it may take, as the model is told them: a closed list, a string's alone.
    enum: list[Annotated[str, Field(min_length=1, max_length=100)]] | None = Field(
        default=None, min_length=1, max_length=MOST_VALUES
    )


class FixedField(WireModel):
    """A field the request always carries, set here and never by the model (`source: "phone"`), over the model's."""

    name: str = Field(max_length=64, pattern=A_NAME)
    value: Scalar


class HttpTool(WireModel):
    """A request to the business's own API the model may make, its answer what the model reads."""

    name: str = Field(max_length=64, pattern=A_NAME)
    description: str = Field(min_length=1, max_length=1000)
    method: Method = "GET"
    url: str = Field(min_length=8, max_length=2000)
    headers: list[Header] = Field(default_factory=list[Header], max_length=16)
    params: list[Param] = Field(default_factory=list[Param], max_length=MOST_PARAMS)
    fixed: list[FixedField] = Field(default_factory=list[FixedField], max_length=MOST_PARAMS)
    # What the agent says as the request starts, when it has grown long, and when it failed.
    announce: str | None = Field(default=None, max_length=LONGEST_LINE)
    delayed: str | None = Field(default=None, max_length=LONGEST_LINE)
    delayed_after_s: float = Field(default=DELAYED_AFTER_S, gt=0, le=LONGEST_TOOL_S)
    failed: str | None = Field(default=None, max_length=LONGEST_LINE)
    timeout_s: float = Field(default=TOOL_TIMEOUT_S, gt=0, le=LONGEST_TOOL_S)


class CollectedField(Param):
    """One thing to collect from the caller: its name, its type, what it is, and the values it may take."""


class Collect(WireModel):
    """Data collection: fields the agent gathers, the call ended once the required ones are in."""

    fields: list[CollectedField] = Field(min_length=1, max_length=MOST_FIELDS)
    end_when_done: bool = True
    # What the agent says once every required field is in, as an instruction to the model.
    closing: str = Field(default="Thank the caller, say goodbye, and end the call.", max_length=1000)
    # Where the fields are posted when the call ends, with the transcript; nowhere when null.
    send_to: str | None = Field(default=None, max_length=2000)
    headers: list[Header] = Field(default_factory=list[Header], max_length=16)


class Greeting(WireModel):
    """How the agent opens a call: `say` the words, or `reply` what the model reads first."""

    say: str | None = Field(default=None, max_length=1000)
    reply: str | None = Field(default=None, max_length=1000)

    @model_validator(mode="after")
    def _one_of_them(self) -> Self:
        if (self.say is None) == (self.reply is None):
            raise ValueError("a greeting is one of two things: `say` the words, or `reply` what the model reads first")
        return self


# The framework tells an agent how to write on the channel a call is on: speech on a call, WhatsApp's
# formatting, plain text by SMS, Markdown in a website's chat. An agent that writes its own for a
# channel is told that instead, and the framework's own on every channel it leaves out.
class ChannelRules(WireModel):
    """How the agent writes on a channel, where it is not the framework's own way: one text a channel."""

    # A spoken call, by phone or from a page.
    voice: str | None = Field(default=None, min_length=1, max_length=LONGEST_CHANNEL_RULES)
    # A written chat on a website.
    chat: str | None = Field(default=None, min_length=1, max_length=LONGEST_CHANNEL_RULES)
    whatsapp: str | None = Field(default=None, min_length=1, max_length=LONGEST_CHANNEL_RULES)
    sms: str | None = Field(default=None, min_length=1, max_length=LONGEST_CHANNEL_RULES)
    email: str | None = Field(default=None, min_length=1, max_length=LONGEST_CHANNEL_RULES)
    # A Facebook Page's Messenger, and the Instagram account linked to it.
    messenger: str | None = Field(default=None, min_length=1, max_length=LONGEST_CHANNEL_RULES)
    instagram: str | None = Field(default=None, min_length=1, max_length=LONGEST_CHANNEL_RULES)


class Definition(WireModel):
    """A Studio agent: its instructions, how it opens, its tools, what it collects, how it writes on a channel."""

    instructions: str = Field(min_length=1, max_length=LONGEST_INSTRUCTIONS)
    greeting: Greeting | None = None
    tools: list[HttpTool] = Field(default_factory=list[HttpTool], max_length=MOST_TOOLS)
    collect: Collect | None = None
    channel_rules: ChannelRules | None = None
