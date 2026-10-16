"""Drift: each day's stage latencies and verdicts by agent and version, folded at the seal."""

import logging
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from hashlib import sha256
from typing import Any, Literal

from pydantic import TypeAdapter
from sqlalchemy.ext.asyncio import AsyncSession

from pinecall_runtime.calls import histogram
from pinecall_runtime.calls.repository.drift import DriftRepository, Where
from pinecall_runtime.calls.repository.heads import HeadRepository
from pinecall_runtime.calls.repository.refold import RefoldRepository
from pinecall_runtime.exceptions import ValidationError
from pinecall_runtime.kit.auth import Scope
from pinecall_runtime.wire.base import Entry
from pinecall_runtime.wire.events import AgentTurnEnded, UserTurnEnded, event_of
from pinecall_runtime.wire.metrics import TurnMetadata
from pinecall_runtime.wire.scores import CallScore

type Stage = Literal["stt", "llm", "tts"]
# A turn's stage, the vendor and the model its report named ('' for none).
type StageKey = tuple[Stage, str, str]
# A judge by name and by the hash of the question it asked.
type JudgeKey = tuple[str, str]

logger = logging.getLogger(__name__)

# The table cannot key a null: a call that ran on no version of its scope's settings is 0.
NO_VERSION = 0
# skipped and deferred were never settled, so they count on neither side.
SETTLED = frozenset({"held", "broken"})
# Calls named per read of the heads while rebuilding; each is folded in its own transaction.
A_PAGE = 500


@dataclass(frozen=True)
class StageSample:
    """One stage on one vendor and model: its turns, their seconds counted, the ears' confidence."""

    turns: int = 0
    buckets: tuple[int, ...] = tuple(histogram.empty())
    confidence_sum: float = 0.0
    confidence_turns: int = 0


@dataclass(frozen=True)
class StageTally:
    """A stage sample read by rank: its turns, median, p95 and mean confidence."""

    turns: int
    median_s: float | None
    p95_s: float | None
    confidence: float | None


@dataclass(frozen=True)
class Verdict:
    """One judge's settled verdict on a call, under the hash of the question it asked."""

    judge: str
    criteria: str
    held: bool


@dataclass(frozen=True)
class JudgeRead:
    """One judge on one side: its verdicts held and settled, and the questions it asked."""

    held: int
    judged: int
    criteria: frozenset[str]

    @property
    def pass_rate(self) -> float | None:
        """The share of its settled verdicts that held; None when none settled."""
        return self.held / self.judged if self.judged else None


@dataclass(frozen=True)
class Side:
    """One side of a drift: a day, a version, or both."""

    day: date | None = None
    version: int | None = None


@dataclass(frozen=True)
class Tally:
    """One side of an agent's drift: its stages and judges, and the versions its calls ran."""

    stages: dict[StageKey, StageSample] = field(default_factory=dict[StageKey, StageSample])
    judges: dict[str, JudgeRead] = field(default_factory=dict[str, JudgeRead])
    versions: frozenset[int] = frozenset()


@dataclass(frozen=True)
class JudgeMoved:
    """A judge on both sides, and how far its pass rate moved."""

    name: str
    before: JudgeRead | None
    after: JudgeRead | None
    moved: float | None
    criteria_changed: bool


@dataclass(frozen=True)
class StageMoved:
    """A stage on both sides, and how far its median and p95 moved."""

    stage: Stage
    vendor: str | None
    model: str | None
    before: StageTally | None
    after: StageTally | None
    median_moved_s: float | None
    p95_moved_s: float | None


@dataclass(frozen=True)
class WindowStage:
    """One stage over a window, versions added: by vendor and model."""

    stage: Stage
    vendor: str | None
    model: str | None
    tally: StageTally


@dataclass(frozen=True)
class Rebuilt:
    """What a rebuild folded again."""

    calls: int
    folded: int


VERDICTS: TypeAdapter[list[Verdict]] = TypeAdapter(list[Verdict])


# The seal's: a call is folded once, and folded again (judged again) only its verdicts change.
async def fold(session: AsyncSession, call: str, entries: Sequence[Entry], score: CallScore) -> bool:
    """Count a sealed call's stages and verdicts into its day; False for a call never started."""
    head = await HeadRepository(session).head_of_call(call)
    if head is None or head.scope is None or head.started_at is None:
        return False
    where = _where(head.scope, head.agent, _day_of(head.started_at), head.versions.config)
    verdicts = _verdicts_of(score)
    ran, failed = _tools_of(entries)
    repository = DriftRepository(session)
    dumped = VERDICTS.dump_python(verdicts, mode="json")
    if await repository.claim(call, where, dumped, ran, failed):
        await repository.add_stages(where, _sample_rows(_samples_of(entries)))
        await repository.add_verdicts(where, _verdict_rows(_tallied(verdicts, sign=1)))
        return True
    counted_raw = await repository.verdicts_counted(call)
    counted = [] if counted_raw is None else VERDICTS.validate_python(counted_raw)
    if counted == verdicts:
        return True
    changed = dict(_tallied(counted, sign=-1))
    for key, (passes, fails) in _tallied(verdicts, sign=1).items():
        before = changed.get(key, (0, 0))
        changed[key] = (before[0] + passes, before[1] + fails)
    await repository.add_verdicts(where, _verdict_rows(changed))
    await repository.recount(call, dumped)
    return True


# Every agent's when agent is None; its days and versions are added together either way.
async def stages_of_window(
    session: AsyncSession, scope: Scope, first: date, last: date, agent: str | None
) -> list[WindowStage]:
    """Every stage of the scope's days first to last by vendor and model, versions added."""
    rows = await DriftRepository(session).window_stages(scope, first, last, agent)
    merged = _merged_stages(rows)
    return [
        WindowStage(stage, vendor or None, model or None, tallied_stage(sample))
        for (stage, vendor, model), sample in sorted(merged.items())
    ]


# What moved most comes first: a judge by its pass rate, a stage by its median.
def compared(before: Tally, after: Tally) -> tuple[list[JudgeMoved], list[StageMoved]]:
    """Each judge and each stage on both sides, and how far it moved, the most moved first."""
    judges = [
        _judge_moved(name, before.judges.get(name), after.judges.get(name))
        for name in sorted({*before.judges, *after.judges})
    ]
    stages = [
        _stage_moved(key, before.stages.get(key), after.stages.get(key))
        for key in sorted({*before.stages, *after.stages})
    ]
    judges.sort(key=lambda judge: -abs(judge.moved) if judge.moved is not None else 1.0)
    stages.sort(key=lambda row: -abs(row.median_moved_s) if row.median_moved_s is not None else 1.0)
    return judges, stages


async def tally(session: AsyncSession, scope: Scope, agent: str, side: Side) -> Tally:
    """One side of an agent's drift in the scope: its stages, its judges, its versions."""
    repository = DriftRepository(session)
    stages = await repository.side_stages(scope, agent, side.day, side.version)
    verdicts = await repository.side_verdicts(scope, agent, side.day, side.version)
    judges: dict[str, JudgeRead] = {}
    for row in verdicts:
        before = judges.get(row.judge, JudgeRead(0, 0, frozenset()))
        judges[row.judge] = JudgeRead(
            held=before.held + row.held,
            judged=before.judged + row.held + row.broken,
            criteria=before.criteria | {row.criteria},
        )
    ran = {int(row.config_version) for row in (*stages, *verdicts)}
    return Tally(
        stages=_merged_stages(stages),
        judges=judges,
        versions=frozenset(version for version in ran if version != NO_VERSION),
    )


async def rebuild(session: AsyncSession, *, org: str | None, since: float | None) -> Rebuilt:
    """Forget the drift of the calls the flags name and fold each sealed one again from its log."""
    repository = DriftRepository(session)
    refold = RefoldRepository(session)
    await repository.forget(org, None if since is None else _day_of(since))
    calls = folded = 0
    after = ""
    while names := await repository.sealed_after(org, since, after, A_PAGE):
        for call in names:
            entries = await refold.entries_of(call)
            score = _last_score(entries)
            if score is not None and await fold(session, call, entries, score):
                folded += 1
            calls += 1
        after = names[-1]
    return Rebuilt(calls=calls, folded=folded)


def tallied_stage(sample: StageSample) -> StageTally:
    """A sample read by rank."""
    return StageTally(
        turns=sample.turns,
        median_s=histogram.rank(sample.buckets, histogram.MEDIAN),
        p95_s=histogram.rank(sample.buckets, histogram.P95),
        confidence=sample.confidence_sum / sample.confidence_turns if sample.confidence_turns else None,
    )


def _samples_of(entries: Iterable[Entry]) -> dict[StageKey, StageSample]:
    seconds: dict[StageKey, list[float]] = {}
    turns: dict[StageKey, int] = {}
    confidence: dict[StageKey, list[float]] = {}
    for entry in entries:
        for key, value, sure in _stages_of(entry):
            turns[key] = turns.get(key, 0) + 1
            if value is not None:
                seconds.setdefault(key, []).append(value)
            if sure is not None:
                confidence.setdefault(key, []).append(sure)
    return {
        key: StageSample(
            turns=count,
            buckets=tuple(histogram.count_times(seconds.get(key, ()))),
            confidence_sum=sum(confidence.get(key, ())),
            confidence_turns=len(confidence.get(key, ())),
        )
        for key, count in turns.items()
    }


def _tools_of(entries: Iterable[Entry]) -> tuple[int, int]:
    results = [entry for entry in entries if entry.type == "tool.result"]
    return len(results), sum(1 for entry in results if entry.data.get("error") is not None)


def _verdicts_of(score: CallScore) -> list[Verdict]:
    return [
        Verdict(judge.name, _criteria_hash(judge.criteria), judge.verdict == "held")
        for judge in score.judges
        if judge.verdict in SETTLED
    ]


# A judge's question as drift keys it: its hash, so a changed question is told apart.
def _criteria_hash(criteria: str) -> str:
    return sha256(criteria.encode()).hexdigest()


def _day_of(started_at: float) -> date:
    return datetime.fromtimestamp(started_at, UTC).date()


def _stages_of(entry: Entry) -> list[tuple[StageKey, float | None, float | None]]:
    if entry.type not in {"turn.user", "turn.agent"}:
        return []
    try:
        turn = event_of(entry)
    except ValidationError:
        logger.warning("call %s: seq %d is not a turn drift reads", entry.call, entry.seq)
        return []
    found: list[tuple[StageKey, float | None, float | None]] = []
    if isinstance(turn, UserTurnEnded):
        heard = turn.metrics
        delay, sure = heard.transcription_delay, turn.transcript_confidence
        if delay is not None or sure is not None:
            found.append((_key("stt", heard.stt_metadata), delay, sure))
    if isinstance(turn, AgentTurnEnded):
        answered = turn.metrics
        if answered.llm_node_ttft is not None:
            found.append((_key("llm", answered.llm_metadata), answered.llm_node_ttft, None))
        if answered.tts_node_ttfb is not None:
            found.append((_key("tts", answered.tts_metadata), answered.tts_node_ttfb, None))
    return found


def _key(stage: Stage, metadata: TurnMetadata | None) -> StageKey:
    if metadata is None:
        return (stage, "", "")
    return (stage, metadata.model_provider or "", metadata.model_name or "")


def _where(scope: Scope, agent: str, day: date, version: int | None) -> Where:
    return Where(scope.org, scope.env, scope.holder, agent, day, NO_VERSION if version is None else version)


def _tallied(verdicts: Iterable[Verdict], *, sign: int) -> dict[JudgeKey, tuple[int, int]]:
    tallied: dict[JudgeKey, tuple[int, int]] = {}
    for item in verdicts:
        passes, fails = tallied.get((item.judge, item.criteria), (0, 0))
        tallied[(item.judge, item.criteria)] = (passes + sign, fails) if item.held else (passes, fails + sign)
    return tallied


def _sample_rows(samples: Mapping[StageKey, StageSample]) -> list[dict[str, Any]]:
    return [
        {
            "stage": stage,
            "vendor": vendor,
            "model": model,
            "turns": sample.turns,
            "buckets": list(sample.buckets),
            "confidence_sum": sample.confidence_sum,
            "confidence_turns": sample.confidence_turns,
        }
        for (stage, vendor, model), sample in samples.items()
    ]


def _verdict_rows(tallied: Mapping[JudgeKey, tuple[int, int]]) -> list[dict[str, Any]]:
    return [
        {"judge": judge, "criteria": criteria, "held": passes, "broken": fails}
        for (judge, criteria), (passes, fails) in tallied.items()
    ]


def _merged_stages(rows: Iterable[Any]) -> dict[StageKey, StageSample]:
    merged: dict[StageKey, StageSample] = {}
    for row in rows:
        key: StageKey = (row.stage, row.vendor, row.model)
        before = merged.get(key, StageSample())
        merged[key] = StageSample(
            turns=before.turns + row.turns,
            buckets=tuple(histogram.added(before.buckets, row.buckets)),
            confidence_sum=before.confidence_sum + row.confidence_sum,
            confidence_turns=before.confidence_turns + row.confidence_turns,
        )
    return merged


def _judge_moved(name: str, before: JudgeRead | None, after: JudgeRead | None) -> JudgeMoved:
    rates = (None if before is None else before.pass_rate, None if after is None else after.pass_rate)
    return JudgeMoved(
        name=name,
        before=before,
        after=after,
        moved=None if None in rates else _moved(rates[0], rates[1]),
        criteria_changed=before is not None and after is not None and before.criteria != after.criteria,
    )


def _stage_moved(key: StageKey, before: StageSample | None, after: StageSample | None) -> StageMoved:
    stage, vendor, model = key
    first = None if before is None else tallied_stage(before)
    second = None if after is None else tallied_stage(after)
    return StageMoved(
        stage=stage,
        vendor=vendor or None,
        model=model or None,
        before=first,
        after=second,
        median_moved_s=None if first is None or second is None else _moved(first.median_s, second.median_s),
        p95_moved_s=None if first is None or second is None else _moved(first.p95_s, second.p95_s),
    )


def _moved(before: float | None, after: float | None) -> float | None:
    return None if before is None or after is None else after - before


def _last_score(entries: Sequence[Entry]) -> CallScore | None:
    scored = next((entry for entry in reversed(entries) if entry.type == "call.score"), None)
    if scored is None:
        return None
    try:
        return CallScore.model_validate(scored.data)
    except ValueError:
        logger.warning("call %s: its call.score is not one drift reads", scored.call)
        return None
