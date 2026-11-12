"""A call's slowest turns, taken from its log at the seal: where the caller's wait went, and read back."""

import logging
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date

from sqlalchemy.ext.asyncio import AsyncSession

from runtime.calls import folds
from runtime.exceptions import ValidationError
from runtime.insights.models import SlowTurn
from runtime.insights.repository.drift import Days, DriftRepository, TurnToKeep
from runtime.wire.base import Entry
from runtime.wire.events import AgentTurnEnded, ToolCall, UserTurnEnded, event_of
from runtime.wire.parts import ToolResult

logger = logging.getLogger(__name__)

# Each call keeps this many turns, the ones that made the caller wait longest.
KEPT_PER_CALL = 3
THE_LINE = frozenset({"call.ringing", "call.dialing", "call.started"})


@dataclass(frozen=True, slots=True)
class SlowTurns:
    """A window's slowest turns, the slowest first: the window's last day, its days, whose agent."""

    day: date
    days: int
    agent: str | None
    turns: Sequence[SlowTurn]


def rows_of(call: str, entries: Sequence[Entry]) -> list[TurnToKeep]:
    """The call's slowest turns as the table takes them, slowest first."""
    ordered = sorted(entries, key=lambda entry: entry.seq)
    name = _name_of(call, ordered)
    spent = _sum_tool_seconds_by_speech(ordered)
    heard: float | None = None
    found: list[TurnToKeep] = []
    for entry in ordered:
        turn = _turn_of(entry)
        if isinstance(turn, UserTurnEnded):
            heard = turn.metrics.transcription_delay
        elif isinstance(turn, AgentTurnEnded):
            if turn.metrics.e2e_latency is not None:
                found.append(
                    TurnToKeep(
                        call=call,
                        seq=entry.seq,
                        at=entry.ts,
                        name=name,
                        e2e_s=turn.metrics.e2e_latency,
                        hears_s=heard,
                        thinks_s=turn.metrics.llm_node_ttft,
                        tools_s=spent.get(turn.speech_id),
                        speaks_s=turn.metrics.tts_node_ttfb,
                    )
                )
            heard = None
    found.sort(key=lambda row: (-row.e2e_s, row.seq))
    return found[:KEPT_PER_CALL]


# Each call keeps its three slowest turns when it is sealed; this lists the window's slowest of them.
async def slowest_of_window(session: AsyncSession, days: Days, limit: int) -> SlowTurns:
    """The slowest turns of the window's days with where each one's wait went, the slowest first."""
    turns = await DriftRepository(session).list_slowest_turns(days, limit)
    return SlowTurns(day=days.last, days=days.count, agent=days.agent, turns=turns)


# Who the caller was is what the call's facts say: the name its line carried.
def _name_of(call: str, entries: Sequence[Entry]) -> str | None:
    facts = folds.CallFacts(call=call)
    for entry in entries:
        if entry.type in THE_LINE:
            facts = folds.fold(facts, entry)
    return facts.name


# A tool belongs to the turn whose speech asked for it; a tool with no time on its result adds none.
def _sum_tool_seconds_by_speech(entries: Sequence[Entry]) -> dict[str, float]:
    speech_of: dict[str, str] = {}
    spent: dict[str, float] = {}
    for entry in entries:
        if entry.type == "tool.call":
            asked = _tool_call_of(entry)
            if asked is not None and asked.speech_id is not None:
                speech_of[asked.call_id] = asked.speech_id
        elif entry.type == "tool.result":
            result = _tool_result_of(entry)
            speech = None if result is None else speech_of.get(result.call_id)
            if result is not None and result.duration_s is not None and speech is not None:
                spent[speech] = spent.get(speech, 0.0) + result.duration_s
    return spent


def _turn_of(entry: Entry) -> AgentTurnEnded | UserTurnEnded | None:
    if entry.type not in {"turn.user", "turn.agent"}:
        return None
    try:
        turn = event_of(entry)
    except ValidationError:
        logger.warning("call %s: seq %d is not a turn drift reads", entry.call, entry.seq)
        return None
    return turn if isinstance(turn, AgentTurnEnded | UserTurnEnded) else None


def _tool_call_of(entry: Entry) -> ToolCall | None:
    try:
        return ToolCall.parse(entry.data, entry.type)
    except ValidationError:
        return None


def _tool_result_of(entry: Entry) -> ToolResult | None:
    try:
        return ToolResult.parse(entry.data, entry.type)
    except ValidationError:
        return None
