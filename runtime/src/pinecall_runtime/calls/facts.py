"""What is known of every call without folding its log: the facts row, folded as entries land."""

from collections.abc import Sequence
from dataclasses import dataclass, replace
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from pinecall_runtime.calls.models import CallFact
from pinecall_runtime.calls.repository.facts import COLUMNS, FactsRepository
from pinecall_runtime.exceptions import ValidationError
from pinecall_runtime.kit.text import JsonObject
from pinecall_runtime.wire.base import Entry, WireModel
from pinecall_runtime.wire.events import (
    EVENTS,
    AgentTurnEnded,
    CallDialing,
    CallEnded,
    CallRinging,
    CallStarted,
    CallSummary,
    UserTurnEnded,
    event_of,
)
from pinecall_runtime.wire.metrics import ModelUsage
from pinecall_runtime.wire.parts import PLATFORM, Cost
from pinecall_runtime.wire.room import RoomOpened
from pinecall_runtime.wire.scores import CallScore
from pinecall_runtime.wire.state import State

# The judge whose broken verdict raises the promise flag (evals' library).
PROMISES = "promises"

# skipped and deferred are not judged.
SETTLED = frozenset({"held", "broken"})

ENDED_BY_A_PERSON = frozenset({"transferred", "supervisor_ended"})

# A whisper is not one of these: the agent keeps the conversation.
A_PERSON_TOOK_PART = frozenset(
    {
        "supervisor.took_over",
        "supervisor.said",
        "supervisor.ended",
        "supervisor.transferred",
        "call.transferred",
    }
)

# A web call is spoken only once a room opens.
SPOKEN_CHANNEL = "phone"

# What a list shows of a call, read off its state: the fields of a CallRow the log decides. Written
# to the facts row at the seal, so a list of two hundred sealed calls folds no log; the cursor
# (`seq`) rides along as the row's last_seq.
LINE_FIELDS = (
    "seq",
    "status",
    "channel",
    "direction",
    "from",
    "to",
    "caller",
    "started_at",
    "ended_at",
    "end_reason",
    "outcome",
    "cost",
    "attention",
)

# What a summary's cost is folded by: a model's rows are the stage its usage was metered in,
# whatever their unit (a voice priced by the second of audio, as Gemini's is); a row no usage names
# (a phone leg) is its unit's stage; the box's own rows (PLATFORM) are the platform's.
STAGES = ("llm", "stt", "tts", "phone", "platform")
STAGE_OF_USAGE = {"llm_usage": "llm", "stt_usage": "stt", "tts_usage": "tts"}
STAGE_OF_UNIT = {
    "input_tokens": "llm",
    "cached_input_tokens": "llm",
    "cache_creation_tokens": "llm",
    "output_tokens": "llm",
    "characters": "tts",
    "audio_seconds": "stt",
    "minutes": "phone",
}

# The types the fold reads; every other entry leaves a call's facts as they are, so a group of
# only those never locks or reads a facts row (most of a call's entries: its metrics, its transcripts).
FOLDED_TYPES = (
    frozenset(
        name
        for name, model in EVENTS.items()
        if model
        in (
            CallRinging,
            CallDialing,
            CallStarted,
            CallEnded,
            CallSummary,
            CallScore,
            RoomOpened,
            UserTurnEnded,
            AgentTurnEnded,
        )
    )
    | A_PERSON_TOOK_PART
)


# Every field comes from some entry, so the row can always be folded again from the log. In
# memory it is a frozen value, compared whole to know whether the row moved.
@dataclass(frozen=True, slots=True)
class CallFacts:
    """One call as its lists, counts and inbox see it."""

    call: str
    channel: str | None = None
    direction: str | None = None
    from_number: str | None = None
    to_number: str | None = None
    name: str | None = None
    # The inbox key: the app's contact id, else the number or the visitor id.
    contact: str | None = None
    persona: str | None = None
    spoken: bool = False
    ended_at: float | None = None
    end_reason: str | None = None
    outcome: str | None = None
    cost_usd: float | None = None
    cost_llm_usd: float | None = None
    cost_stt_usd: float | None = None
    cost_tts_usd: float | None = None
    cost_phone_usd: float | None = None
    cost_platform_usd: float | None = None
    judged: int | None = None
    held: int | None = None
    passed: bool | None = None
    reason: str | None = None
    escalated: bool = False
    promised: bool = False
    e2e: tuple[float, ...] = ()
    heard_at: tuple[float, ...] = ()
    last_text: str | None = None
    last_at: float | None = None
    last_in: bool | None = None
    lent: tuple[str, ...] = ()
    # Not a fold: what a simulated caller's model and voice cost, kept when the simulation ends.
    caller_cost_usd: float = 0.0
    # Not a fold either: the state's line, written at the seal (`line_of`), None while the call is live.
    line: JsonObject | None = None

    @property
    def score(self) -> dict[str, object] | None:
        """The score as the wire carries it, or None while no judge settled."""
        if not self.judged:
            return None
        return {
            "held": self.held or 0,
            "judged": self.judged,
            "passed": self.passed is not False,
            "reason": self.reason,
        }

    @property
    def flags(self) -> list[str]:
        """The review flags raised, in the wire's order."""
        raised = (("escalated", self.escalated), ("low_score", self.passed is False), ("promise", self.promised))
        return [flag for flag, up in raised if up]

    def as_row(self) -> dict[str, Any]:
        """As the call_facts row is written."""
        row = {name: getattr(self, name) for name in COLUMNS}
        return {**row, "e2e": list(self.e2e), "heard_at": list(self.heard_at), "lent": list(self.lent)}


def line_of(state: State) -> JsonObject:
    """What a list shows of the call, as its state says it now."""
    dumped = state.dump()
    return {name: dumped.get(name) for name in LINE_FIELDS}


def facts_of(model: CallFact) -> CallFacts:
    """The facts a call_facts row holds."""
    values = {name: getattr(model, name) for name in COLUMNS}
    row: dict[str, Any] = {
        **values,
        "e2e": tuple(model.e2e),
        "heard_at": tuple(model.heard_at),
        "lent": tuple(model.lent),
    }
    return CallFacts(**row)


def fold(facts: CallFacts, entry: Entry) -> CallFacts:
    """The facts with what the entry says; an entry that says nothing to them, unchanged."""
    if entry.call is None or entry.ephemeral:
        return facts
    match _readable(entry):
        case CallRinging() | CallDialing() | CallStarted() as line:
            return _on_the_line(facts, line)
        case CallEnded() | CallSummary() as over:
            return _over(facts, over)
        case CallScore() as score:
            return _scored(facts, score)
        case RoomOpened():
            return replace(facts, spoken=True)
        case UserTurnEnded() | AgentTurnEnded() as turn:
            return _turn_folded(facts, entry, turn)
        case _ if entry.type in A_PERSON_TOOK_PART:
            return replace(facts, escalated=True)
        case _:
            return facts


# On the writer's transaction, so folds land in seq order under the head rows' locks. The entries
# are each call's in seq order: every call's row is locked at once, folded in memory, and the rows
# that moved are written in one statement.
async def record(session: AsyncSession, entries: Sequence[Entry]) -> None:
    """Fold the entries into their calls' facts rows, in the transaction they are written in."""
    by_call: dict[str, list[Entry]] = {}
    for entry in entries:
        if entry.call is not None and not entry.ephemeral and entry.type in FOLDED_TYPES:
            by_call.setdefault(entry.call, []).append(entry)
    if not by_call:
        return
    repository = FactsRepository(session)
    known = {call: facts_of(row) for call, row in (await repository.lock(sorted(by_call))).items()}
    written: list[dict[str, Any]] = []
    for call, kept in by_call.items():
        facts = known.get(call, CallFacts(call=call))
        folded = facts
        for entry in kept:
            folded = fold(folded, entry)
        if folded != facts:
            written.append(folded.as_row())
    await repository.write_all(written)


def _readable(entry: Entry) -> WireModel | None:
    try:
        return event_of(entry)
    except ValidationError:
        return None


def _on_the_line(facts: CallFacts, line: CallRinging | CallDialing | CallStarted) -> CallFacts:
    caller = line.caller
    direction = line.direction if isinstance(line, CallStarted) else None
    persona = line.persona if isinstance(line, CallStarted) else None
    return replace(
        facts,
        channel=line.channel,
        direction=direction or ("outbound" if isinstance(line, CallDialing) else "inbound"),
        from_number=line.from_,
        to_number=line.to,
        name=facts.name if caller is None else caller.name or facts.name,
        contact=(caller.id if caller is not None and caller.id else None) or line.from_,
        persona=persona or facts.persona,
        spoken=facts.spoken or line.channel == SPOKEN_CHANNEL,
    )


# The reason the call ended with stands; the summary's is taken only when there was none.
def _over(facts: CallFacts, over: CallEnded | CallSummary) -> CallFacts:
    if isinstance(over, CallEnded):
        return replace(
            facts,
            ended_at=over.ended_at,
            end_reason=facts.end_reason or over.reason,
            escalated=facts.escalated or over.reason in ENDED_BY_A_PERSON,
        )
    return replace(
        facts,
        outcome=over.outcome,
        cost_usd=over.cost.usd,
        end_reason=facts.end_reason or over.reason,
        **_cost_by_stage(over.cost, over.usage),
    )


def _cost_by_stage(cost: Cost, usage: Sequence[ModelUsage]) -> dict[str, Any]:
    staged = {(used.provider, used.model): STAGE_OF_USAGE[used.type] for used in usage if used.type in STAGE_OF_USAGE}
    summed: dict[str, float] = dict.fromkeys(STAGES, 0.0)
    for row in cost.rows:
        if row.provider == PLATFORM:
            stage = "platform"
        else:
            stage = staged.get((row.provider, row.model), STAGE_OF_UNIT[row.unit])
        summed[stage] += row.usd
    return {f"cost_{stage}_usd": round(usd, 6) for stage, usd in summed.items()}


# A verdict replaces the one before it whole.
def _scored(facts: CallFacts, score: CallScore) -> CallFacts:
    settled = [judge for judge in score.judges if judge.verdict in SETTLED]
    broken = [item for item in settled if item.verdict == "broken"]
    passed = score.passed if score.passed is not None else (not broken if settled else None)
    return replace(
        facts,
        judged=len(settled),
        held=len(settled) - len(broken),
        passed=passed,
        reason=broken[0].reason if broken else None,
        promised=any(item.name == PROMISES for item in broken),
    )


def _turn_folded(facts: CallFacts, entry: Entry, turn: UserTurnEnded | AgentTurnEnded) -> CallFacts:
    if isinstance(turn, UserTurnEnded):
        return replace(facts, heard_at=(*facts.heard_at, entry.ts), last_text=turn.text, last_at=entry.ts, last_in=True)
    e2e = turn.metrics.e2e_latency
    return replace(
        facts, e2e=facts.e2e if e2e is None else (*facts.e2e, e2e), last_text=turn.text, last_at=entry.ts, last_in=False
    )
