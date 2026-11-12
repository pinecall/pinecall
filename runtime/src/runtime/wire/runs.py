"""An eval run as it is kept and read: the calls it opened, each golden's scores under each model, the matrix."""

from typing import Literal

from runtime.kit.text import JsonObject
from runtime.wire.base import WireModel

# `failed` is the run itself; a golden that failed is a score, not a status.
type RunStatus = Literal["running", "done", "failed"]


class JudgeScore(WireModel):
    """One judge's verdict on one golden under one model."""

    metric: str
    # A pass is 1, a fail is 0.
    score: float
    passed: bool
    reason: str
    criteria: str
    judge_calls: int


class OpenedCall(WireModel):
    """The call one golden opened under one model."""

    golden: str
    model: str
    call: str


# `asked` is set on a cell that did not hold, and null when the run kept no requests.
class ScoreRow(WireModel):
    """Every judge's verdict on one golden under one model, and the call's own summary."""

    model: str
    golden: str
    scores: list[JudgeScore]
    summary: JsonObject | None
    asked: list[JsonObject] | None = None


class Failure(WireModel):
    """One judge that did not hold, and the cell it broke on."""

    model: str
    golden: str
    metric: str


class ScoreMatrix(WireModel):
    """Models by goldens: the axes in the order the cells came, one row per cell."""

    models: list[str]
    goldens: list[str]
    metrics: list[str]
    # A count, not a price: a judge's tokens are billed with the rest of the model usage.
    judge_calls: int
    runs: list[ScoreRow]
    failures: list[Failure]


# The run's document (`eval_runs.document`): written whole at every change, so a run is followed while it
# goes, and read by whichever release a gateway runs.
class Run(WireModel):
    """An eval run: the calls it opened, the matrix judged so far, and why it stopped early."""

    id: str
    agent: str
    started_at: float
    finished_at: float | None
    status: RunStatus
    calls: list[OpenedCall]
    matrix: ScoreMatrix | None
    error: str | None
