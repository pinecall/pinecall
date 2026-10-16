"""What the judges said about a call: call.score, one judgment per judge, and what else was spent."""

from typing import Literal

from pydantic import AliasChoices, Field

from pinecall_runtime.enums import Env
from pinecall_runtime.wire.base import WireModel
from pinecall_runtime.wire.parts import ScoreVerdict

type SpentOn = Literal["try", "generate", "propose"]


class JudgmentEvidence(WireModel):
    """Where in the call's own log a judgment is about."""

    seqs: list[int]
    said: str | None = None


class Judgment(WireModel):
    """One judge's answer about one call."""

    name: str
    verdict: ScoreVerdict
    criteria: str
    reason: str
    evidence: JudgmentEvidence
    choice: str | None = None
    score: int | None = None


class JudgedBy(WireModel):
    """Who gave a score: the judge model, and one hash of every question the panel asked."""

    provider: str | None
    model: str | None
    criteria: str


class CallScore(WireModel):
    """The last entry of a call: what the judges said at hang-up, one row per judge."""

    passed: bool | None = None
    not_judged: str | None = None
    judges: list[Judgment]
    panel: list[str] | None = None
    judge_calls: int
    evals: int = 0
    own_key: bool = False
    judge_cost_usd: float | None = Field(
        default=None, validation_alias=AliasChoices("judge_cost_usd", "judge_cost_eur")
    )
    judged_by: JudgedBy | None = None


class EvalsSpent(WireModel):
    """The harness asked a model outside a call's score: a judge tried, personas, a diagnosis."""

    kind: SpentOn
    name: str
    env: Env
    calls: list[str]
    evals: int
    judge_calls: int
    judge_cost_usd: float | None = None
    own_key: bool = False
