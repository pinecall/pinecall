"""Drift: a sealed call folded into its day by agent and version, and two days or versions of an agent compared."""

import logging
import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from hashlib import sha256
from typing import Any

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from runtime.actor import Scope
from runtime.agents import service as agents
from runtime.calls import service as calls
from runtime.enums import Env, Stage
from runtime.exceptions import ValidationError
from runtime.insights.models import StageDay
from runtime.insights.repository.drift import DriftRepository, Side, StageToAdd, VerdictsToAdd, Where
from runtime.insights.service import slow_turns, tool_days
from runtime.kit import histogram
from runtime.kit.time import day_of, now, opening_of
from runtime.wire.base import Entry
from runtime.wire.events import AgentTurnEnded, UserTurnEnded, event_of
from runtime.wire.metrics import TurnMetadata
from runtime.wire.scores import CallScore

# A turn's stage, the vendor and the model its report named ('' for none).
type StageKey = tuple[Stage, str, str]
# A judge by name and by the hash of the question it asked.
type JudgeKey = tuple[str, str]

logger = logging.getLogger(__name__)

# The table cannot key a null: a call that ran on no version of its scope's settings is 0.
NO_VERSION = 0
# skipped and deferred were never settled, so they count on neither side.
SETTLED = frozenset({"held", "broken"})
# Calls named per read of the heads while rebuilding.
A_PAGE = 500
A_VERSION = re.compile(r"v(\d+)")
# No day on either side: no version was set "between" them.
NEVER = datetime.fromtimestamp(0, UTC)


@dataclass(frozen=True, slots=True)
class StageSample:
    """One stage on one vendor and model: its turns, their seconds counted, the ears' confidence; read by rank."""

    turns: int = 0
    buckets: tuple[int, ...] = tuple(histogram.empty())
    confidence_sum: float = 0.0
    confidence_turns: int = 0

    @property
    def median_s(self) -> float | None:
        """The median of its seconds; None when no turn was timed."""
        return histogram.rank(self.buckets, histogram.MEDIAN)

    @property
    def p95_s(self) -> float | None:
        """The tail of its seconds; None when no turn was timed."""
        return histogram.rank(self.buckets, histogram.P95)

    @property
    def confidence(self) -> float | None:
        """How sure the ears were, on average; None when no turn said."""
        return self.confidence_sum / self.confidence_turns if self.confidence_turns else None


@dataclass(frozen=True, slots=True)
class Verdict:
    """One judge's settled verdict on a call, under the hash of the question it asked."""

    judge: str
    criteria: str
    held: bool


@dataclass(frozen=True, slots=True)
class JudgeRead:
    """One judge on one side: its verdicts held and settled, and the questions it asked."""

    held: int
    judged: int
    criteria: frozenset[str]

    @property
    def pass_rate(self) -> float | None:
        """The share of its settled verdicts that held; None when none settled."""
        return self.held / self.judged if self.judged else None


@dataclass(frozen=True, slots=True)
class Tally:
    """One side of an agent's drift: its stages and judges, and the versions its calls ran."""

    stages: dict[StageKey, StageSample] = field(default_factory=dict[StageKey, StageSample])
    judges: dict[str, JudgeRead] = field(default_factory=dict[str, JudgeRead])
    versions: frozenset[int] = frozenset()


@dataclass(frozen=True, slots=True)
class JudgeMoved:
    """A judge on both sides, and how far its pass rate moved."""

    name: str
    before: JudgeRead | None
    after: JudgeRead | None
    moved: float | None
    criteria_changed: bool


@dataclass(frozen=True, slots=True)
class StageMoved:
    """A stage on both sides, and how far its median and p95 moved."""

    stage: Stage
    vendor: str | None
    model: str | None
    before: StageSample | None
    after: StageSample | None
    median_moved_s: float | None
    p95_moved_s: float | None


@dataclass(frozen=True, slots=True)
class SideRead:
    """One side of a drift as asked, a day or a version, and the versions its calls ran."""

    day: date | None
    version: int | None
    versions: list[int]


@dataclass(frozen=True, slots=True)
class VersionNoted:
    """A version of the agent's settings a side ran or that was set between: who, when, why."""

    version: int
    holder: str
    author: str
    note: str | None
    set_at: datetime
    ran_before: bool
    ran_after: bool


@dataclass(frozen=True, slots=True)
class Drift:
    """What moved between two days or versions of an agent, the most moved first, and the versions that explain it."""

    agent: str
    env: Env
    before: SideRead
    after: SideRead
    judges: list[JudgeMoved]
    stages: list[StageMoved]
    versions: list[VersionNoted]


@dataclass(frozen=True, slots=True)
class Rebuilt:
    """What a rebuild folded again."""

    calls: int
    folded: int


# ── a call folded ──


# Drift is a measure of the day, not of the call: a fold that breaks is logged and the call seals
# all the same, and `pinecall-runtime drift rebuild` counts it later.
async def fold_call(session: AsyncSession, call: str, entries: Sequence[Entry], score: CallScore) -> None:
    """Count the call's stages, verdicts, tools and slowest turns into its day's drift, or log why not."""
    try:
        async with session.begin_nested():
            await _fold(session, call, entries, score)
    except SQLAlchemyError:
        logger.warning("call %s was not counted into its day's drift", call, exc_info=True)


async def rebuild(session: AsyncSession, *, org: str | None, since: float | None) -> Rebuilt:
    """Forget the drift of the calls the flags name and fold each sealed one again from its log."""
    repository = DriftRepository(session)
    await repository.forget(org, None if since is None else day_of(since))
    read = folded = 0
    after = ""
    while names := await repository.list_sealed_after(org, since, after, A_PAGE):
        for call in names:
            entries = await calls.list_entries(session, call)
            score = _last_score(entries)
            if score is not None and await _fold(session, call, entries, score):
                folded += 1
            read += 1
        after = names[-1]
    return Rebuilt(calls=read, folded=folded)


# The seal's: a call is folded once, and folded again (judged again) only its verdicts change.
async def _fold(session: AsyncSession, call: str, entries: Sequence[Entry], score: CallScore) -> bool:
    head = await calls.find_head(session, call)
    if head is None or head.scope is None or head.started_at is None:
        return False
    where = _where(head.scope, head.agent, day_of(head.started_at), head.versions.settings)
    verdicts = _verdicts_of(score)
    ran, failed = _count_tools(entries)
    repository = DriftRepository(session)
    if await repository.claim(call, where, _dump_verdicts(verdicts), ran, failed):
        await repository.add_stages(where, _sample_rows(_samples_of(entries)))
        await repository.add_tools(where, tool_days.rows_of(entries))
        await repository.add_slow_turns(where, slow_turns.rows_of(call, entries))
        await repository.add_verdicts(where, _verdict_rows(_tally_verdicts(verdicts, sign=1)))
        return True
    counted = _read_verdicts(await repository.lock_verdicts(call) or [])
    if counted == verdicts:
        return True
    changed = dict(_tally_verdicts(counted, sign=-1))
    for key, (passes, fails) in _tally_verdicts(verdicts, sign=1).items():
        before = changed.get(key, (0, 0))
        changed[key] = (before[0] + passes, before[1] + fails)
    await repository.add_verdicts(where, _verdict_rows(changed))
    await repository.recount(call, _dump_verdicts(verdicts))
    return True


# ── read back ──


# Folded when each call was sealed: two days or two versions read a few rows each.
async def drift_between(
    session: AsyncSession, scope: Scope, agent: str, before: str | None, after: str | None
) -> Drift:
    """What moved between two days or versions of an agent, and the versions run or set."""
    first, second = _sides(before, after)
    earlier, later = await tally(session, scope, agent, first), await tally(session, scope, agent, second)
    judges, stages = compare(earlier, later)
    days = [side.day for side in (first, second) if side.day is not None]
    since = opening_of(min(days)) if days else NEVER
    until = opening_of(max(days)) + timedelta(days=1) if days else NEVER
    ran = earlier.versions | later.versions
    noted = await agents.list_noted_versions(session, scope, agent, ran, since, until)
    return Drift(
        agent=agent,
        env=scope.env,
        before=SideRead(first.day, first.version, sorted(earlier.versions)),
        after=SideRead(second.day, second.version, sorted(later.versions)),
        judges=judges,
        stages=stages,
        versions=[
            VersionNoted(
                version=row.version,
                holder=row.holder,
                author=row.author,
                note=row.note,
                set_at=row.set_at,
                ran_before=row.version in earlier.versions,
                ran_after=row.version in later.versions,
            )
            for row in noted
        ],
    )


async def tally(session: AsyncSession, scope: Scope, agent: str, side: Side) -> Tally:
    """One side of an agent's drift in the scope: its stages, its judges, its versions."""
    repository = DriftRepository(session)
    stages = await repository.list_side_stages(scope, agent, side)
    verdicts = await repository.list_side_verdicts(scope, agent, side)
    judges: dict[str, JudgeRead] = {}
    for row in verdicts:
        before = judges.get(row.judge, JudgeRead(0, 0, frozenset()))
        judges[row.judge] = JudgeRead(
            held=before.held + row.held,
            judged=before.judged + row.held + row.broken,
            criteria=before.criteria | {row.criteria},
        )
    ran = {row.config_version for row in stages} | {row.config_version for row in verdicts}
    return Tally(
        stages=merge_stages(stages),
        judges=judges,
        versions=frozenset(version for version in ran if version != NO_VERSION),
    )


# What moved most comes first: a judge by its pass rate, a stage by its median.
def compare(before: Tally, after: Tally) -> tuple[list[JudgeMoved], list[StageMoved]]:
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


# Two days by default: today and the day before it, in UTC.
def _sides(before: str | None, after: str | None) -> tuple[Side, Side]:
    second = _side_of(after) if after is not None else Side(day=now().date())
    if before is not None:
        return _side_of(before), second
    if second.day is None:
        raise ValidationError("a drift between versions names both: before=v3&after=v4")
    return Side(day=second.day - timedelta(days=1)), second


# A side is typed as a day (2026-11-12) or as a version of the agent's settings (v3).
def _side_of(text: str) -> Side:
    version = A_VERSION.fullmatch(text)
    if version is not None:
        return Side(version=int(version.group(1)))
    try:
        return Side(day=date.fromisoformat(text))
    except ValueError as refused:
        raise ValidationError(f"{text!r} is neither a day (YYYY-MM-DD) nor a version (v3)") from refused


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


def _count_tools(entries: Iterable[Entry]) -> tuple[int, int]:
    results = [entry for entry in entries if entry.type == "tool.result"]
    return len(results), sum(1 for entry in results if entry.data.get("error") is not None)


def _verdicts_of(score: CallScore) -> list[Verdict]:
    return [
        Verdict(judge.name, _hash_criteria(judge.criteria), judge.verdict == "held")
        for judge in score.judges
        if judge.verdict in SETTLED
    ]


# A judge's question as drift keys it: its hash, so a changed question is told apart.
def _hash_criteria(criteria: str) -> str:
    return sha256(criteria.encode()).hexdigest()


# As `drift_calls.verdicts` keeps them, and as it gives them back.
def _dump_verdicts(verdicts: Iterable[Verdict]) -> list[dict[str, Any]]:
    return [{"judge": item.judge, "criteria": item.criteria, "held": item.held} for item in verdicts]


def _read_verdicts(kept: Iterable[Mapping[str, Any]]) -> list[Verdict]:
    return [Verdict(str(item["judge"]), str(item["criteria"]), bool(item["held"])) for item in kept]


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
            found.append((_key(Stage.stt, heard.stt_metadata), delay, sure))
    if isinstance(turn, AgentTurnEnded):
        answered = turn.metrics
        if answered.llm_node_ttft is not None:
            found.append((_key(Stage.llm, answered.llm_metadata), answered.llm_node_ttft, None))
        if answered.tts_node_ttfb is not None:
            found.append((_key(Stage.tts, answered.tts_metadata), answered.tts_node_ttfb, None))
    return found


def _key(stage: Stage, metadata: TurnMetadata | None) -> StageKey:
    if metadata is None:
        return (stage, "", "")
    return (stage, metadata.model_provider or "", metadata.model_name or "")


def _where(scope: Scope, agent: str, day: date, version: int | None) -> Where:
    return Where(scope.org, scope.env, scope.holder, agent, day, NO_VERSION if version is None else version)


def _tally_verdicts(verdicts: Iterable[Verdict], *, sign: int) -> dict[JudgeKey, tuple[int, int]]:
    tallied: dict[JudgeKey, tuple[int, int]] = {}
    for item in verdicts:
        passes, fails = tallied.get((item.judge, item.criteria), (0, 0))
        tallied[(item.judge, item.criteria)] = (passes + sign, fails) if item.held else (passes, fails + sign)
    return tallied


def _sample_rows(samples: Mapping[StageKey, StageSample]) -> list[StageToAdd]:
    return [
        StageToAdd(
            stage=stage,
            vendor=vendor,
            model=model,
            turns=sample.turns,
            buckets=sample.buckets,
            confidence_sum=sample.confidence_sum,
            confidence_turns=sample.confidence_turns,
        )
        for (stage, vendor, model), sample in samples.items()
    ]


def _verdict_rows(tallied: Mapping[JudgeKey, tuple[int, int]]) -> list[VerdictsToAdd]:
    return [VerdictsToAdd(judge, criteria, passes, fails) for (judge, criteria), (passes, fails) in tallied.items()]


def merge_stages(rows: Iterable[StageDay]) -> dict[StageKey, StageSample]:
    """The rows as one sample per stage, vendor and model: their days and versions added bucket by bucket."""
    merged: dict[StageKey, StageSample] = {}
    for row in rows:
        key: StageKey = (row.stage, row.vendor, row.model)
        before = merged.get(key, StageSample())
        merged[key] = StageSample(
            turns=before.turns + row.turns,
            buckets=tuple(histogram.add(before.buckets, row.buckets)),
            confidence_sum=before.confidence_sum + row.confidence_sum,
            confidence_turns=before.confidence_turns + row.confidence_turns,
        )
    return merged


def _judge_moved(name: str, before: JudgeRead | None, after: JudgeRead | None) -> JudgeMoved:
    return JudgeMoved(
        name=name,
        before=before,
        after=after,
        moved=_shift(None if before is None else before.pass_rate, None if after is None else after.pass_rate),
        criteria_changed=before is not None and after is not None and before.criteria != after.criteria,
    )


def _stage_moved(key: StageKey, before: StageSample | None, after: StageSample | None) -> StageMoved:
    stage, vendor, model = key
    return StageMoved(
        stage=stage,
        vendor=vendor or None,
        model=model or None,
        before=before,
        after=after,
        median_moved_s=None if before is None or after is None else _shift(before.median_s, after.median_s),
        p95_moved_s=None if before is None or after is None else _shift(before.p95_s, after.p95_s),
    )


def _shift(before: float | None, after: float | None) -> float | None:
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
