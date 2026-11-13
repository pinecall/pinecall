"""A finished call as a judge reads it: turns, tool calls, states, evidence, the caller's rule."""

import json
import logging
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, replace
from typing import Literal

from runtime.agents.declaration import Declaration, ToolSpec
from runtime.enums import Direction
from runtime.exceptions import ValidationError
from runtime.kit.text import Json, JsonObject
from runtime.session import service as session
from runtime.wire.base import Entry, WireModel
from runtime.wire.events import (
    AgentTurnEnded,
    CallEnded,
    CallStarted,
    CallSummary,
    ConfirmDeclined,
    ConfirmGranted,
    ConfirmRequest,
    DocsSources,
    ErrorEvent,
    MemoryOps,
    StateChanged,
    ToolCall,
    UserTurnEnded,
    event_of,
)
from runtime.wire.parts import EndedBy, SideEffect, ToolResult
from runtime.wire.room import A_SIMULATED_CALLER
from runtime.wire.scores import CallScore

# livekit's two speakers.
type Role = Literal["user", "assistant"]

# The entries the consent rule reads, in the order the log wrote them.
type GateKind = Literal["tool.call", "confirm.request", "confirm.granted", "confirm.declined"]

logger = logging.getLogger(__name__)

METRICS = "metrics."

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
class Failed:
    """One error the call logged, and whether its session recovered from it."""

    seq: int
    code: str
    message: str
    recoverable: bool


# The one reading of a call's log. Until 2026-11 a seal folded the log into this and threw it away,
# then read the log six more times with four parsers to keep the call as a case; two of those raised
# on an entry of an older shape, where this one leaves the entry out.
@dataclass(frozen=True, slots=True)
class Transcript:
    """A finished call: its turns, the gate trace, its states, its evidence, and who was on the other end."""

    call: str = ""
    agent: str = ""
    turns: tuple[Said, ...] = ()
    gate: tuple[GateLine, ...] = ()
    # Every state the call was in, in order: the view is rendered from them, not stored.
    states: tuple[JsonObject, ...] = ()
    # Knowledge text and the facts memory recalled.
    evidence: tuple[str, ...] = ()
    summary: JsonObject | None = None
    # What the simulated caller expected of the agent, off call.started; empty for a person.
    expects: tuple[str, ...] = ()
    # A persona played the caller: named on call.started, or the spoken caller's leg.
    simulated: bool = False
    # The persona that played the caller, when call.started names one.
    persona: str | None = None
    declaration: Declaration | None = None
    # Off call.started; None for a log that never started.
    direction: Direction | None = None
    # When the call began, seconds since the epoch; off call.started too.
    began: float | None = None
    # The call's last call.score, the verdict a judge may write again after the seal; None before it.
    score: CallScore | None = None
    # Every error the call logged, in order, and who ended it (None for a log with no end): what a
    # replay's checks read, which until 2026-11 folded the log a third time for them.
    errors: tuple[Failed, ...] = ()
    ended_by: EndedBy | None = None

    def lines_by(self, role: Role) -> tuple[str, ...]:
        """What one side said, turn by turn."""
        return tuple(turn.text for turn in self.turns if turn.role == role)

    @property
    def tool_calls(self) -> tuple[Called, ...]:
        """Every tool call the agent made, in order."""
        return tuple(called for turn in self.turns for called in turn.calls)

    @property
    def caller_lines(self) -> tuple[str, ...]:
        """The lines the caller said, the blank ones left out."""
        return tuple(line for line in self.lines_by(CALLER) if line.strip())


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
def transcript_of(entries: Sequence[Entry], declaration: Declaration | None) -> Transcript:
    """The transcript of a finished call, read from its log."""
    read = [(entry, data) for entry in entries if (data := read_entry(entry)) is not None]
    filed = _Filed(tools={} if declaration is None else dict(declaration.tools_by_name))
    for entry, data in read:
        _file(filed, entry, data)
    knowledge = () if declaration is None or not declaration.knowledge else (declaration.knowledge,)
    recalled = [fact.text for _, data in read if isinstance(data, MemoryOps) for op in data.ops for fact in op.facts]
    summary = next((data for _, data in reversed(read) if isinstance(data, CallSummary)), None)
    started = next((data for _, data in read if isinstance(data, CallStarted)), None)
    return Transcript(
        call=call_of(entries),
        agent=entries[0].agent if entries else "",
        turns=_turns(filed),
        gate=tuple(filed.gate),
        states=tuple(dict(data.state) for _, data in read if isinstance(data, StateChanged)),
        evidence=(*knowledge, *recalled),
        summary=None if summary is None else summary.dump(),
        expects=() if started is None else tuple(started.expects or ()),
        simulated=is_simulated_start(started),
        persona=None if started is None else started.persona,
        declaration=declaration,
        direction=None if started is None else started.direction,
        began=None if started is None else started.started_at,
        score=score_of(entries),
        errors=tuple(
            Failed(entry.seq, data.code, data.message, data.recoverable)
            for entry, data in read
            if isinstance(data, ErrorEvent)
        ),
        ended_by=next((data.ended_by for _, data in reversed(read) if isinstance(data, CallEnded)), None),
    )


def call_of(entries: Sequence[Entry]) -> str:
    """The call a log is of, "" for a log that names none."""
    return next((entry.call for entry in entries if entry.call is not None), "")


def score_of(entries: Sequence[Entry]) -> CallScore | None:
    """The call's last call.score, the verdict a judge may write again after the seal; None before it."""
    scored = next((entry for entry in reversed(entries) if entry.type == "call.score"), None)
    read = None if scored is None else read_entry(scored)
    return read if isinstance(read, CallScore) else None


def is_simulated_start(started: CallStarted | None) -> bool:
    """Whether call.started says a simulated caller, not a person, was on the other end."""
    return started is not None and (started.persona is not None or started.from_ == A_SIMULATED_CALLER)


# A persona's call, or a golden's played by the simulated caller: each is one simulation billed. A
# start this version cannot read says nobody simulated: the seal that asks goes on without it.
def is_simulated(entries: Sequence[Entry]) -> bool:
    """Whether a simulated caller, not a person, was on the other end of the call."""
    for entry in entries:
        if entry.type == "call.started":
            started = read_entry(entry)
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


# What an org's policy has a call open with is said by the worker before the greeting and logged as a
# turn of the agent's. Until 2026-11 a judge read it as the agent's first message, and one asked
# whether every turn was one message broke every recorded call on the notice and the greeting.
def conversation_of(transcript: Transcript, *, platforms: int | None = None) -> str:
    """Every turn and tool call of the call under its log position; the turn at `platforms` is the platform's."""
    return "\n".join(line for turn in transcript.turns for line in _lines_of(turn, _speaker_of(turn, platforms)))


# An entry of an older shape is left out of the transcript, not the whole call refused.
def read_entry(entry: Entry) -> WireModel | None:
    """The entry's data as the model its type names; None, and said in the log, for one that does not read."""
    try:
        return event_of(entry)
    except ValidationError:
        logger.warning("call %s: seq %d is not a %s the transcript reads", entry.call, entry.seq, entry.type)
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
    turns.extend(_unspoken(filed, {turn.speech_id for turn in turns if turn.role == AGENT}))
    turns.sort(key=lambda turn: turn.seq)
    return tuple(turns)


# A tool the model called without a word, on a call over before it answered (a tool that hung up),
# has no agent turn to ride: its calls fell out of the transcript, and `expect.tools` read "ran no tool
# at all" on a call whose log held the call (2026-10-24). It is a turn that said nothing.
def _unspoken(filed: _Filed, spoken: set[str]) -> list[Said]:
    turns: list[Said] = []
    for speech, tools in filed.called.items():
        if speech in spoken:
            continue
        ids = {tool.call_id for tool in tools}
        seq = min((line.seq for line in filed.gate if line.kind == "tool.call" and line.call_id in ids), default=0)
        turns.append(
            Said(role=AGENT, text="", seq=seq, speech_id=speech, calls=tuple(_tool_call_of(t, filed) for t in tools))
        )
    return turns


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
        calls=tuple(_tool_call_of(tool, filed) for tool in filed.called.get(speech, ())),
    )


def _tool_call_of(tool: ToolCall, filed: _Filed) -> Called:
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


def _speaker_of(turn: Said, platforms: int | None) -> str:
    if turn.role == CALLER:
        return "caller"
    return "platform" if turn.seq == platforms else "agent"


def _lines_of(turn: Said, who: str) -> list[str]:
    lines = [f"#{turn.seq} {who}: {turn.text}"]
    for called in turn.calls:
        arguments = json.dumps(called.arguments, ensure_ascii=False)
        lines.append(f"#{turn.seq} [tool call: {called.name}({arguments})]")
        if called.answer is not None:
            label = "tool error" if called.failed else "tool answer"
            lines.append(f"#{turn.seq} [{label}: {called.answer}]")
    return lines
