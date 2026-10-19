"""Studio's shapes: an agent's definition, built in the console, and what its doors read and answer."""

from datetime import datetime
from typing import Any, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, field_serializer, model_validator

from pinecall_runtime.enums import Env

type ParamType = Literal["string", "number", "integer", "boolean"]
type Method = Literal["GET", "POST", "PUT", "PATCH", "DELETE"]

A_NAME = r"^[A-Za-z][A-Za-z0-9_]*$"
# A tool waits this long unless it says, and never longer than the ceiling: a turn is waiting.
TOOL_TIMEOUT_S = 10.0
LONGEST_TOOL_S = 30.0
MOST_TOOLS = 24
MOST_PARAMS = 16
MOST_FIELDS = 24
LONGEST_INSTRUCTIONS = 20_000


class Shape(BaseModel):
    """A part of a definition: unknown keys refused, so a misspelt field is said, never dropped."""

    model_config = ConfigDict(extra="forbid")


class Header(Shape):
    """One header a request carries; its value may name `{{secrets.NAME}}`."""

    name: str = Field(min_length=1, max_length=100, pattern=r"^[A-Za-z0-9-]+$")
    value: str = Field(max_length=2000)


class Param(Shape):
    """One argument the model fills: a path's `{name}`, else the query of a GET or the JSON body."""

    name: str = Field(max_length=64, pattern=A_NAME)
    type: ParamType = "string"
    description: str = Field(default="", max_length=500)
    required: bool = True


class HttpTool(Shape):
    """A request to the business's own API the model may make, its answer what the model reads."""

    name: str = Field(max_length=64, pattern=A_NAME)
    description: str = Field(min_length=1, max_length=1000)
    method: Method = "GET"
    url: str = Field(min_length=8, max_length=2000)
    headers: list[Header] = Field(default_factory=list[Header], max_length=16)
    params: list[Param] = Field(default_factory=list[Param], max_length=MOST_PARAMS)
    announce: str | None = Field(default=None, max_length=300)
    timeout_s: float = Field(default=TOOL_TIMEOUT_S, gt=0, le=LONGEST_TOOL_S)


class CollectedField(Shape):
    """One thing to collect from the caller: its name, its type and what it is."""

    name: str = Field(max_length=64, pattern=A_NAME)
    type: ParamType = "string"
    description: str = Field(default="", max_length=500)
    required: bool = True


class Collect(Shape):
    """Data collection: fields the agent gathers, the call ended once the required ones are in."""

    fields: list[CollectedField] = Field(min_length=1, max_length=MOST_FIELDS)
    end_when_done: bool = True
    # What the agent says once every required field is in, as an instruction to the model.
    closing: str = Field(default="Thank the caller, say goodbye, and end the call.", max_length=1000)
    # Where the fields are posted when the call ends, with the transcript; nowhere when null.
    send_to: str | None = Field(default=None, max_length=2000)
    headers: list[Header] = Field(default_factory=list[Header], max_length=16)


class Greeting(Shape):
    """How the agent opens a call: `say` the words, or `reply` what the model reads first."""

    say: str | None = Field(default=None, max_length=1000)
    reply: str | None = Field(default=None, max_length=1000)

    @model_validator(mode="after")
    def _one_of_them(self) -> Self:
        if (self.say is None) == (self.reply is None):
            raise ValueError("a greeting is one of two things: `say` the words, or `reply` what the model reads first")
        return self


class Definition(Shape):
    """A Studio agent: its instructions, how it opens, its tools, and what it collects."""

    instructions: str = Field(min_length=1, max_length=LONGEST_INSTRUCTIONS)
    greeting: Greeting | None = None
    tools: list[HttpTool] = Field(default_factory=list[HttpTool], max_length=MOST_TOOLS)
    collect: Collect | None = None


# ── the doors ──


class NewAgentRequest(Shape):
    """POST /v1/studio/agents: a name, and what it starts as."""

    name: str = Field(min_length=1, max_length=40)
    definition: Definition | None = None
    note: str = Field(default="", max_length=200)


class SaveRequest(Shape):
    """PUT /v1/studio/agents/{name}: the next release, over the one read; `based_on` null takes any."""

    definition: Definition
    based_on: int | None = None
    note: str = Field(default="", max_length=200)


class DeployRequest(Shape):
    """POST /v1/studio/agents/{name}/deploy: the sandbox's release, newest unless named, into production."""

    release: int | None = None
    note: str = Field(default="", max_length=200)


class TryRequest(Shape):
    """POST /v1/studio/agents/{name}/try: one tool's request sent once, with these arguments."""

    tool: str = Field(max_length=64)
    arguments: dict[str, Any] = Field(default_factory=dict[str, Any])
    # A definition not saved yet, as the editor holds it; the saved one when null.
    definition: Definition | None = None


class TryResponse(BaseModel):
    """What came back: the status, the body as the model would read it, and how long it took."""

    status: int | None
    body: Any = None
    error: str | None = None
    duration_ms: int


class StudioAgent(BaseModel):
    """One Studio agent in one env: its newest release, its definition, who saved it, and when."""

    name: str
    env: Env
    release: int
    definition: Definition
    author: str
    note: str
    saved_at: datetime
    stopped: bool

    @field_serializer("saved_at")
    def _saved(self, at: datetime) -> float:
        return at.timestamp()


class StudioAgentList(BaseModel):
    """GET /v1/studio/agents: the org's Studio agents in the env, by name."""

    agents: list[StudioAgent]
