"""A finished call as a judge reads it: turns, tool calls, states, evidence, the caller's rule."""

import json
import logging
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, replace
from typing import Literal

from livekit.agents.evals import Verdict
from livekit.agents.llm import ChatContext, ChatItem, ChatMessage, FunctionCall, FunctionCallOutput

from pinecall_runtime.agents.declaration import AgentConfig, ToolSpec
from pinecall_runtime.enums import Direction
from pinecall_runtime.exceptions import ValidationError
from pinecall_runtime.kit.text import Json, JsonObject
from pinecall_runtime.session import service as session
from pinecall_runtime.wire.base import Entry
from pinecall_runtime.wire.events import (
    AgentTurnEnded,
    CallStarted,
    CallSummary,
    ConfirmDeclined,
    ConfirmGranted,
    ConfirmRequest,
    DocsSources,
    EventReceived,
    MemoryOps,
    StateChanged,
    ToolCall,
    UserTurnEnded,
    event_of,
)
from pinecall_runtime.wire.parts import ScoreVerdict, SideEffect, ToolResult

# livekit's two speakers.
type Role = Literal["user", "assistant"]

# The entries the consent rule reads, in the order the log wrote them.
type GateKind = Literal["tool.call", "confirm.request", "confirm.granted", "confirm.declined"]

logger = logging.getLogger(__name__)

PUNCTUATION = ".,;:¿?¡!()\"'"
METRICS = "metrics."
# The caller's leg a spoken simulation publishes under, and the `from` a written one carries.
A_SIMULATED_CALLER = "simulated_caller"

# livekit's three words; `skipped`, `na` and `classified` are ours alone: never asked, did not
# apply, and a choice or a score.
VERDICT_WORDS: dict[Verdict, ScoreVerdict] = {"pass": "held", "fail": "broken", "maybe": "deferred"}

AGENT: Role = "assistant"
CALLER: Role = "user"


@dataclass(frozen=True, slots=True)
class Called:
    """One tool call of a turn: its arguments, and the text the model read back; None: no answer."""

    call_id: str
    name: str
    arguments: JsonObject
    answer: str | None = None
    failed: bool = False
    description: str | None = None


@dataclass(frozen=True, slots=True)
class Arrived:
    """One fact that reached the call from outside, at the seq that places it between turns."""

    seq: int
    name: str
    data: JsonObject
    source: str


@dataclass(frozen=True, slots=True)
class Said:
    """One turn: who, what, livekit's own metric names beside it, what it read and what it ran."""

    role: Role
    text: str
    seq: int = 0
    speech_id: str = ""
    interrupted: bool = False
    metrics: Mapping[str, Json] = field(default_factory=dict[str, Json])
    # The metrics.* entries of the same speech, as written.
    blocks: tuple[JsonObject, ...] = ()
    retrieved: tuple[str, ...] = ()
    calls: tuple[Called, ...] = ()


@dataclass(frozen=True, slots=True)
class GateLine:
    """A tool call or a confirmation, in log order; the side effect comes from the declaration."""

    seq: int
    kind: GateKind
    call_id: str
    tool: str
    audience: str | None = None
    side_effect: SideEffect | None = None


@dataclass(frozen=True, slots=True)
class Case:
    """A finished call: its turns, the gate trace, the facts that arrived, and its evidence."""

    call: str = ""
    agent: str = ""
    turns: tuple[Said, ...] = ()
    gate: tuple[GateLine, ...] = ()
    arrived: tuple[Arrived, ...] = ()
    # Every state the call was in, in order: the view is rendered from them, not stored.
    states: tuple[JsonObject, ...] = ()
    # Knowledge text and the facts memory recalled.
    evidence: tuple[str, ...] = ()
    summary: JsonObject | None = None
    # What the simulated caller expected of the agent, off call.started; empty for a person.
    expects: tuple[str, ...] = ()
    # A persona played the caller: named on call.started, or the spoken caller's leg.
    simulated: bool = False
    declared: AgentConfig | None = None
    # Off call.started; None for a log that never started.
    direction: Direction | None = None
    # When the call began, seconds since the epoch; off call.started too.
    began: float | None = None


@dataclass(frozen=True)
class _Filed:
    """The entries a turn is built from, filed by the speech or the tool call they belong to."""

    tools: Mapping[str, ToolSpec]
    said: list[tuple[Entry, UserTurnEnded | AgentTurnEnded]] = field(
        default_factory=list[tuple[Entry, UserTurnEnded | AgentTurnEnded]]
    )
    called: dict[str, list[ToolCall]] = field(default_factory=dict[str, list[ToolCall]])
    results: dict[str, ToolResult] = field(default_factory=dict[str, ToolResult])
    sources: dict[str, list[str]] = field(default_factory=dict[str, list[str]])
    # What a turn's lookup read before the agent's turn had a speech id (every turn lookup does,
    # written or spoken): the next agent turn's, by log position.
    unclaimed: list[tuple[int, list[str]]] = field(default_factory=list[tuple[int, list[str]]])
    blocks: dict[str, list[JsonObject]] = field(default_factory=dict[str, list[JsonObject]])
    gate: list[GateLine] = field(default_factory=list[GateLine])


# Tool calls and what retrieval showed go on the agent's turn alone, or evidence counts them twice.
def case_of(entries: Sequence[Entry], declared: AgentConfig | None) -> Case:
    """The case of a finished call, read from its log."""
    read = [(entry, data) for entry in entries if (data := _read(entry)) is not None]
    filed = _Filed(tools={} if declared is None else dict(declared.tools_by_name))
    for entry, data in read:
        _file(filed, entry, data)
    knowledge = () if declared is None or not declared.knowledge else (declared.knowledge,)
    recalled = [fact.text for _, data in read if isinstance(data, MemoryOps) for op in data.ops for fact in op.facts]
    summary = next((data for _, data in reversed(read) if isinstance(data, CallSummary)), None)
    started = next((data for _, data in read if isinstance(data, CallStarted)), None)
    return Case(
        call=next((entry.call for entry in entries if entry.call is not None), ""),
        agent=entries[0].agent if entries else "",
        turns=_turns(filed),
        gate=tuple(filed.gate),
        arrived=tuple(
            Arrived(entry.seq, data.name, dict(data.data), data.source)
            for entry, data in read
            if isinstance(data, EventReceived)
        ),
        states=tuple(dict(data.state) for _, data in read if isinstance(data, StateChanged)),
        evidence=(*knowledge, *recalled),
        summary=None if summary is None else summary.dump(),
        expects=() if started is None else tuple(started.expects or ()),
        simulated=is_simulated_start(started),
        declared=declared,
        direction=None if started is None else started.direction,
        began=None if started is None else started.started_at,
    )


def is_simulated_start(started: CallStarted | None) -> bool:
    """Whether call.started says a simulated caller, not a person, was on the other end."""
    return started is not None and (started.persona is not None or started.from_ == A_SIMULATED_CALLER)


# A persona's call, or a golden's played by the simulated caller: each is one simulation billed. A
# start this version cannot read says nobody simulated: the seal that asks goes on without it.
def is_simulated(entries: Sequence[Entry]) -> bool:
    """Whether a simulated caller, not a person, was on the other end of the call."""
    for entry in entries:
        if entry.type == "call.started":
            started = _read(entry)
            return is_simulated_start(started if isinstance(started, CallStarted) else None)
    return False


def gate_line(entry: Entry, data: ConfirmRequest | ConfirmGranted | ConfirmDeclined) -> GateLine:
    """A confirmation as a line of the gate trace; the side effect is left to the declaration."""
    kind: GateKind = (
        "confirm.request"
        if isinstance(data, ConfirmRequest)
        else "confirm.granted"
        if isinstance(data, ConfirmGranted)
        else "confirm.declined"
    )
    return GateLine(entry.seq, kind, data.call_id, data.tool, data.audience)


# livekit's judges take a ChatContext alone.
def as_chat(case: Case) -> ChatContext:
    """The turns as livekit's judges read them, every tool call and its answer included."""
    return ChatContext(items=[item for turn in case.turns for item in _items_of(turn)])


def said_by(case: Case, role: Role) -> tuple[str, ...]:
    """What one side said, turn by turn."""
    return tuple(turn.text for turn in case.turns if turn.role == role)


def calls_of(case: Case) -> tuple[Called, ...]:
    """Every tool call the agent made, in order."""
    return tuple(called for turn in case.turns for called in turn.calls)


def words_of(text: str) -> set[str]:
    """The text's words, case-folded, without the punctuation around them."""
    return {word.strip(PUNCTUATION).casefold() for word in text.split()}


def verdict_word(verdict: Verdict) -> ScoreVerdict:
    """A verdict of livekit's in the word the log writes it with."""
    return VERDICT_WORDS[verdict]


def conversation_of(case: Case) -> str:
    """Every turn and tool call of the call, each line starting with its log position."""
    return "\n".join(line for turn in case.turns for line in _lines_of(turn))


# An entry of an older shape is left out of the case, not the whole case refused.
def _read(entry: Entry) -> object:
    try:
        return event_of(entry)
    except ValidationError:
        logger.warning("call %s: seq %d is not a %s the case reads", entry.call, entry.seq, entry.type)
        return None


def _file(filed: _Filed, entry: Entry, data: object) -> None:
    match data:
        case UserTurnEnded() | AgentTurnEnded():
            filed.said.append((entry, data))
        case ToolCall():
            filed.called.setdefault(data.speech_id or "", []).append(data)
            spec = filed.tools.get(data.name)
            effect = None if spec is None else spec.side_effect
            filed.gate.append(GateLine(entry.seq, "tool.call", data.call_id, data.name, None, effect))
        case ToolResult():
            filed.results[data.call_id] = data
        case ConfirmRequest() | ConfirmGranted() | ConfirmDeclined():
            filed.gate.append(gate_line(entry, data))
        case DocsSources() if data.speech_id:
            filed.sources.setdefault(data.speech_id, []).extend(_excerpts(data))
        case DocsSources():
            filed.unclaimed.append((entry.seq, _excerpts(data)))
        case _ if entry.type.startswith(METRICS):
            filed.blocks.setdefault(str(entry.data.get("speech_id") or ""), []).append(entry.data)
        case _:
            return


# An agent turn reads what its own speech looked up, and what a lookup with no speech id read
# after the agent's turn before it: the grounded judge read those facts as made up (2026-10-17).
def _turns(filed: _Filed) -> tuple[Said, ...]:
    turns: list[Said] = []
    claimed_up_to = -1
    for entry, data in filed.said:
        said = _turn(entry, data, filed)
        if said.role == AGENT:
            before = [chunk for seq, chunks in filed.unclaimed if claimed_up_to < seq < entry.seq for chunk in chunks]
            if before:
                said = replace(said, retrieved=(*before, *said.retrieved))
            claimed_up_to = entry.seq
        turns.append(said)
    return tuple(turns)


def _turn(entry: Entry, data: UserTurnEnded | AgentTurnEnded, filed: _Filed) -> Said:
    speech = data.speech_id
    if isinstance(data, UserTurnEnded):
        return Said(
            role=CALLER,
            text=data.text,
            seq=entry.seq,
            speech_id=speech,
            metrics=data.metrics.dump(),
            blocks=tuple(filed.blocks.get(speech, ())),
        )
    return Said(
        role=AGENT,
        text=data.text,
        seq=entry.seq,
        speech_id=speech,
        interrupted=data.interrupted,
        metrics=data.metrics.dump(),
        blocks=tuple(filed.blocks.get(speech, ())),
        retrieved=tuple(filed.sources.get(speech, ())),
        calls=tuple(_called(tool, filed) for tool in filed.called.get(speech, ())),
    )


def _called(tool: ToolCall, filed: _Filed) -> Called:
    answered = filed.results.get(tool.call_id)
    spec = filed.tools.get(tool.name)
    return Called(
        call_id=tool.call_id,
        name=tool.name,
        arguments=dict(tool.arguments),
        answer=None if answered is None else session.result_text(answered),
        failed=answered is not None and answered.error is not None,
        description=None if spec is None else spec.description,
    )


def _excerpts(data: DocsSources) -> list[str]:
    return [
        "\n".join(part for part in (source.heading, source.excerpt) if part)
        for source in data.sources
        if source.excerpt or source.heading
    ]


def _items_of(turn: Said) -> list[ChatItem]:
    items: list[ChatItem] = [ChatMessage(role=turn.role, content=[turn.text], interrupted=turn.interrupted)]
    for called in turn.calls:
        arguments = json.dumps(called.arguments, ensure_ascii=False)
        items.append(FunctionCall(call_id=called.call_id, name=called.name, arguments=arguments))
        if called.answer is not None:
            items.append(
                FunctionCallOutput(
                    call_id=called.call_id, name=called.name, output=called.answer, is_error=called.failed
                )
            )
    return items


def _lines_of(turn: Said) -> list[str]:
    who = "agent" if turn.role == AGENT else "caller"
    lines = [f"#{turn.seq} {who}: {turn.text}"]
    for called in turn.calls:
        arguments = json.dumps(called.arguments, ensure_ascii=False)
        lines.append(f"#{turn.seq} [tool call: {called.name}({arguments})]")
        if called.answer is not None:
            label = "tool error" if called.failed else "tool answer"
            lines.append(f"#{turn.seq} [{label}: {called.answer}]")
    return lines
