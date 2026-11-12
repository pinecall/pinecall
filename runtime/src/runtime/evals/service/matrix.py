"""A run's scores: one check's ruling as a score, a golden's cell under one model, the matrix of the cells."""

from collections.abc import Iterable, Sequence
from dataclasses import dataclass

from runtime.kit.text import JsonObject
from runtime.wire.runs import Failure, JudgeScore, OpenedCall, ScoreMatrix, ScoreRow


# Until 2026-11 a ruling was livekit's `JudgmentResult`, built here and read back through its
# `EvaluationResult` for a number that is 1 or 0.
@dataclass(frozen=True, slots=True)
class Ruling:
    """What a check came to: whether it held, and why."""

    passed: bool
    reason: str


def passing(reason: str) -> Ruling:
    """A ruling that holds."""
    return Ruling(True, reason)


def failing(reason: str) -> Ruling:
    """A ruling that does not."""
    return Ruling(False, reason)


def score_of(metric: str, criteria: str, ruling: Ruling, *, asked: int = 0) -> JudgeScore:
    """A ruling as the run's document keeps it: what it was held to, and the judge model's requests it made."""
    return JudgeScore(
        metric=metric,
        score=1.0 if ruling.passed else 0.0,
        passed=ruling.passed,
        reason=ruling.reason,
        criteria=criteria,
        judge_calls=asked,
    )


# Every cell carries the call's own summary, never a number of its own.
def cell_of(
    opened: OpenedCall, summary: JsonObject | None, scores: Sequence[JudgeScore], requests: Sequence[JsonObject] | None
) -> ScoreRow:
    """One golden under one model; a cell that did not hold carries the requests it was sent."""
    cell = ScoreRow(model=opened.model, golden=opened.golden, scores=list(scores), summary=summary)
    if all(score.passed for score in scores):
        return cell
    return cell.model_copy(update={"asked": None if requests is None else list(requests)})


def matrix_of(cells: Iterable[ScoreRow]) -> ScoreMatrix:
    """The matrix of these cells: the axes in the order they came, and every judge that broke."""
    rows = list(cells)
    return ScoreMatrix(
        models=list(dict.fromkeys(row.model for row in rows)),
        goldens=list(dict.fromkeys(row.golden for row in rows)),
        metrics=list(dict.fromkeys(score.metric for row in rows for score in row.scores)),
        judge_calls=sum(score.judge_calls for row in rows for score in row.scores),
        runs=rows,
        failures=[
            Failure(model=row.model, golden=row.golden, metric=score.metric)
            for row in rows
            for score in row.scores
            if not score.passed
        ],
    )
