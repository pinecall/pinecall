"""The bodies of Studio's endpoints: an agent made, saved, deployed and read, and a tool tried."""

from typing import Any

from pydantic import Field

from runtime.enums import Env
from runtime.kit.schemas import Epoch, Row, Schema
from runtime.wire.studio import Definition


class NewAgentRequest(Schema):
    """POST /v1/studio/agents: a name, and what it starts as."""

    name: str = Field(min_length=1, max_length=40)
    definition: Definition | None = None
    note: str = Field(default="", max_length=200)


class SaveRequest(Schema):
    """PUT /v1/studio/agents/{name}: the next release, over the one read; `based_on` null takes any."""

    definition: Definition
    based_on: int | None = None
    note: str = Field(default="", max_length=200)


class DeployRequest(Schema):
    """POST /v1/studio/agents/{name}/deploy: the sandbox's release, newest unless named, into production."""

    release: int | None = None
    note: str = Field(default="", max_length=200)


class TryRequest(Schema):
    """POST /v1/studio/agents/{name}/try: one tool's request sent once, with these arguments."""

    tool: str = Field(max_length=64)
    arguments: dict[str, Any] = Field(default_factory=dict[str, Any])
    # A definition not saved yet, as the editor holds it; the saved one when null.
    definition: Definition | None = None


class TryResponse(Row):
    """What came back: the status, the body as the model would read it, and how long it took."""

    status: int | None
    body: Any = None
    error: str | None = None
    duration_ms: int


class StudioAgent(Row):
    """One Studio agent in one env: its newest release, its definition, who saved it, and when."""

    name: str
    env: Env
    release: int
    definition: Definition
    author: str
    note: str
    saved_at: Epoch
    stopped: bool


class StudioAgentList(Row):
    """GET /v1/studio/agents: the org's Studio agents in the env, by name."""

    agents: list[StudioAgent]
