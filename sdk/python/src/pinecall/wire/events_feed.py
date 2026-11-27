"""What a feed says of a change no log holds, by id, and what an agent's log spent besides calls."""

from typing import Literal

from pydantic import Field

from pinecall.wire._names import Env
from pinecall.wire.frames import WireModel
from pinecall.wire.metrics import LLMModelUsage
from pinecall.wire.parts import Cost


class AppFailed(WireModel):
    """A hosted app did not build, start or stay up: the org's alert, on no agent's log."""

    app: str
    host: str
    release: int | None = None
    why: str


class OrgQuiet(WireModel):
    """A newborn org with no call that went well: the operators' alert, said once, on no log."""

    org: str
    name: str
    created_at: float
    calls: int
    failed: int


class ReleaseChanged(WireModel):
    """A hosted app's release changed where it stands: uploaded, live, failed or replaced."""

    app: str
    release: int


class RunChanged(WireModel):
    """A run of goldens and cases opened a call, judged one, or finished."""

    run: str
    agent: str
    finished: bool


class WorkerChanged(WireModel):
    """A worker of a fleet was first heard, cordoned, uncordoned, or stopped being heard."""

    worker: str
    fleet: str
    up: bool
    cordoned: bool


class ToolRan(WireModel):
    """A tool of a call answered; its name and seconds, never its arguments or its output."""

    call: str
    agent: str
    name: str
    duration_s: float | None


class ToolFailed(WireModel):
    """A tool of a call failed or timed out; its name and seconds, never what it said."""

    call: str
    agent: str
    name: str
    duration_s: float | None


class JudgeBroke(WireModel):
    """A judge found a sealed call broken; its name, never its reason or its evidence."""

    call: str
    agent: str
    judge: str


class EvalsSpent(WireModel):
    """The harness asked a model outside a call's score: a judge tried, personas, a diagnosis."""

    kind: Literal["try", "generate", "propose"]
    name: str
    # The agent's log is both worlds': the try is counted in the one it was asked in.
    env: Env
    calls: list[str]
    evals: int
    judge_calls: int
    judge_cost_usd: float | None = None
    own_key: bool = False


class ModelSpent(WireModel):
    """A flow asked a model outside a call: one extraction, metered as one written turn."""

    kind: Literal["extract"] = "extract"
    app: str
    flow: str
    run: str
    # The agent's log is both worlds': the request is counted in the one it was asked in.
    env: Env
    turns: int
    usage: list[LLMModelUsage] = Field(default_factory=list[LLMModelUsage])
    cost: Cost
    own_key: bool = False
