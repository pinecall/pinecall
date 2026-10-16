"""The reducer: a log's entries folded into the State the runtime folds them to, entry by entry."""

from collections.abc import Iterable, Mapping
from typing import TypeVar

from pinecall.errors import WireError
from pinecall.wire.events import AgentRegistered, ErrorEvent, LogGap, event_of
from pinecall.wire.events_call import (
    AttentionAnswered,
    AttentionRequested,
    CallDialing,
    CallEnded,
    CallLine,
    CallRinging,
    CallStarted,
    CallSummary,
    CallTransferred,
    ConfirmDeclined,
    ConfirmGranted,
    ConfirmRequest,
    SupervisorReleased,
    SupervisorTookOver,
    SupervisorTransferred,
)
from pinecall.wire.events_turn import (
    AgentStateChanged,
    AgentTranscript,
    AgentTurnEnded,
    Custom,
    DocsSources,
    EventReceived,
    MemoryOps,
    PromptChanged,
    StateChanged,
    ToolCall,
    ToolsChanged,
    UserStateChanged,
    UserTranscript,
    UserTurnEnded,
)
from pinecall.wire.frames import Entry, WireModel
from pinecall.wire.metrics import (
    AvatarMetrics,
    EOTInferenceMetrics,
    EOUMetrics,
    InterruptionMetrics,
    LLMMetrics,
    RealtimeModelMetrics,
    STTMetrics,
    TTSMetrics,
    VADMetrics,
)
from pinecall.wire.parts import ToolResult
from pinecall.wire.room import ParticipantJoined, ParticipantLeft, ParticipantSpeaking, RoomOpened
from pinecall.wire.state import (
    AgentTurn,
    AttentionState,
    CollectedMetrics,
    Confirm,
    CustomNote,
    Gap,
    Handoff,
    LiveTranscript,
    LoggedError,
    Participant,
    PromptBlockState,
    ReceivedEvent,
    Room,
    State,
    ToolRun,
    TransferState,
    UserTurn,
)

_T = TypeVar("_T", ToolRun, Confirm)

UNREADABLE = "unreadable"

NOT_THIS_SHAPE = "{type} at seq {seq} is not the shape this reader knows: {why}"


# Must fold as the TypeScript and Ruby reducers do: the protocol's golden log holds all three.
def reduce(entries: Iterable[Entry]) -> State:
    """Fold the entries, in order, into the State of an empty log."""
    state = initial_state()
    for entry in entries:
        state = apply(state, entry)
    return state


# Built from a mapping because `from` is a Python keyword.
def initial_state() -> State:
    """Return the State of a log nothing was written to."""
    return State.model_validate(
        {
            "seq": 0,
            "agent": "",
            "call": None,
            "status": "idle",
            "channel": None,
            "direction": None,
            "from": None,
            "to": None,
            "caller": None,
            "room": None,
            "started_at": None,
            "ended_at": None,
            "end_reason": None,
            "outcome": None,
            "user_state": None,
            "agent_state": None,
            "live": {"user": None, "agent": None},
            "turns": [],
            "metrics": {block: [] for block in CollectedMetrics.model_fields},
            "tools": [],
            "app_state": {},
            "events": [],
            "prompt": {},
            "tools_visible": [],
            "confirms": [],
            "memory": [],
            "sources": [],
            "handoff": {"active": False, "by": None},
            "held": False,
            "muted": False,
            "transfer": None,
            "attention": None,
            "usage": [],
            "cost": None,
            "routes": [],
            "gaps": [],
            "errors": [],
            "custom": [],
        }
    )


# An old log may hold a shape this version cannot read: it becomes one line of errors and the
# fold goes on, as the other two reducers do. A gap with a snapshot replaces the state whole.
def apply(state: State, entry: Entry) -> State:
    """Fold one entry into the state and return the state it leaves."""
    try:
        data = event_of(entry)
    except WireError as why:
        first_line = str(why).split("\n", 1)[0].strip()
        message = NOT_THIS_SHAPE.format(type=entry.type, seq=entry.seq, why=first_line)
        state.errors.append(LoggedError(seq=entry.seq, code=UNREADABLE, message=message))
    else:
        if isinstance(data, LogGap):
            state = _resumed(state, data)
        _call(state, data)
        _talk(state, data)
        _tools(state, entry, data)
        _room(state, entry, data)
        _people(state, entry, data)
        _metrics(state.metrics, data)
        _notes(state, entry, data)
    state.seq = entry.seq
    state.agent = entry.agent
    if entry.call is not None:
        state.call = entry.call
    return state


def _resumed(state: State, gap: LogGap) -> State:
    resumed = state if gap.snapshot is None else gap.snapshot.model_copy(deep=True)
    resumed.gaps.append(Gap(from_seq=gap.from_seq, to_seq=gap.to_seq))
    return resumed


def _call(state: State, data: WireModel) -> None:
    match data:
        case CallRinging():
            state.status, state.direction = "ringing", "inbound"
            _line(state, data)
        case CallDialing():
            state.status, state.direction = "dialing", "outbound"
            _line(state, data)
        case CallStarted():
            state.status, state.direction, state.started_at = (
                "active",
                data.direction,
                data.started_at,
            )
            _line(state, data)
        case CallEnded():
            state.status, state.ended_at, state.end_reason = "ended", data.ended_at, data.reason
            state.live = LiveTranscript(user=None, agent=None)
            if state.attention is not None and state.attention.status == "open":
                state.attention = state.attention.model_copy(update={"status": "lapsed"})
        case CallLine():
            state.held, state.muted = data.held, data.muted
        case CallSummary():
            state.usage, state.cost, state.outcome = list(data.usage), data.cost, data.outcome
            state.end_reason = state.end_reason or data.reason
        case _:
            pass


def _line(state: State, data: CallRinging | CallDialing | CallStarted) -> None:
    state.channel, state.from_, state.to, state.caller = (
        data.channel,
        data.from_,
        data.to,
        data.caller,
    )


# A turn keeps only the fields that were on the wire, so it is built from what was written.
def _talk(state: State, data: WireModel) -> None:
    match data:
        case UserStateChanged():
            state.user_state = data.state
        case AgentStateChanged():
            state.agent_state = data.state
        case UserTranscript():
            state.live.user = None if data.final else data.text
        case AgentTranscript():
            state.live.agent = None if data.final else _joined(state.live.agent or "", data)
        case UserTurnEnded():
            state.turns.append(UserTurn.model_validate({"role": "user", **data.written()}))
            state.live.user = None
        case AgentTurnEnded():
            state.turns.append(AgentTurn.model_validate({"role": "agent", **data.written()}))
            state.live.agent = None
        case MemoryOps():
            state.memory.extend(data.ops)
        case DocsSources():
            state.sources = list(data.sources)
        case _:
            pass


# A word aligned to the audio (it has a start) comes without its space; a token brings its own.
def _joined(so_far: str, delta: AgentTranscript) -> str:
    glued = not so_far or so_far[-1].isspace() or delta.text[:1].isspace() or delta.start is None
    return f"{so_far}{'' if glued else ' '}{delta.text}"


def _tools(state: State, entry: Entry, data: WireModel) -> None:
    match data:
        case ToolCall():
            run = {**data.written(), "status": "running", "seq": entry.seq}
            state.tools.append(ToolRun.model_validate(run))
        case ToolResult():
            outcome = {k: v for k, v in data.written().items() if k not in {"call_id", "name"}}
            outcome["status"] = "done" if data.error is None else "failed"
            _settled(state.tools, data.call_id, outcome)
        case StateChanged():
            state.app_state = dict(data.state)
        case PromptChanged():
            state.prompt[data.name] = PromptBlockState(
                hash=data.hash, chars=data.chars, seq=entry.seq
            )
        case ToolsChanged():
            state.tools_visible = list(data.visible)
        case ConfirmRequest():
            params = {"tool": data.tool, "call_id": data.call_id, "audience": data.audience}
            state.confirms.append(Confirm(**params, phrase=data.phrase, status="pending"))
        case ConfirmGranted():
            _settled(state.confirms, data.call_id, {"status": "granted", "said": data.said})
        case ConfirmDeclined():
            text = {} if data.said is None else {"said": data.said}
            _settled(
                state.confirms, data.call_id, {"status": "declined", "reason": data.reason, **text}
            )
        case _:
            pass


# The last one with that call_id, since an app may reuse an id across turns.
def _settled(items: list[_T], call_id: str, update: Mapping[str, object]) -> None:
    for index in range(len(items) - 1, -1, -1):
        if items[index].call_id == call_id:
            items[index] = items[index].model_copy(update=update)
            return


# joined_at comes from the entry's ts: the event carries no time.
def _room(state: State, entry: Entry, data: WireModel) -> None:
    match data:
        case RoomOpened():
            state.room = Room(name=data.name, sid=data.sid, participants=[], caller=None)
        case EventReceived():
            fact = {k: v for k, v in data.written().items() if k != "data"}
            state.events.append(ReceivedEvent.model_validate({**fact, "seq": entry.seq}))
        case ParticipantJoined() if state.room is not None:
            arrived = {**data.written(), "joined_at": entry.ts, "speaking": False}
            state.room.participants.append(Participant.model_validate(arrived))
            if data.kind == "caller":
                state.room.caller = data.identity
        case ParticipantLeft() if state.room is not None:
            state.room.participants = [
                seat for seat in state.room.participants if seat.identity != data.identity
            ]
            if state.room.caller == data.identity:
                state.room.caller = None
        case ParticipantSpeaking() if state.room is not None:
            for seat in state.room.participants:
                if seat.identity == data.identity:
                    seat.speaking = data.speaking
        case _:
            pass


# asked_at comes from the entry's ts: the event carries no time.
def _people(state: State, entry: Entry, data: WireModel) -> None:
    match data:
        case CallTransferred():
            by = "agent" if state.transfer is None else state.transfer.by
            status = "done" if data.ok else "failed"
            state.transfer = TransferState(to=data.to, mode=data.mode, status=status, by=by)
        case SupervisorTookOver():
            state.handoff = Handoff(active=True, by=data.by)
        case SupervisorReleased():
            state.handoff = Handoff(active=False, by=None)
        case SupervisorTransferred():
            state.transfer = TransferState(
                to=data.to, mode=data.mode, status="requested", by="supervisor"
            )
        case AttentionRequested():
            state.attention = AttentionState(
                reason=data.reason, wait_s=data.wait_s, status="open", asked_at=entry.ts, by=None
            )
        case AttentionAnswered() if state.attention is not None:
            settled = "answered" if data.ok else "lapsed"
            state.attention = state.attention.model_copy(update={"status": settled, "by": data.by})
        case _:
            pass


def _metrics(blocks: CollectedMetrics, data: WireModel) -> None:
    match data:
        case LLMMetrics():
            blocks.llm.append(data)
        case STTMetrics():
            blocks.stt.append(data)
        case TTSMetrics():
            blocks.tts.append(data)
        case VADMetrics():
            blocks.vad.append(data)
        case EOUMetrics():
            blocks.eou.append(data)
        case EOTInferenceMetrics():
            blocks.eot.append(data)
        case InterruptionMetrics():
            blocks.interruption.append(data)
        case RealtimeModelMetrics():
            blocks.realtime.append(data)
        case AvatarMetrics():
            blocks.avatar.append(data)
        case _:
            pass


# supervisor.said, .whispered and .ended, the tracks, room.sent, call.score and call.attached
# change nothing here: what they caused arrives as turns, prompt changes and call.ended.
def _notes(state: State, entry: Entry, data: WireModel) -> None:
    match data:
        case AgentRegistered():
            state.routes = list(data.routes)
        case ErrorEvent():
            state.errors.append(LoggedError(seq=entry.seq, code=data.code, message=data.message))
        case Custom():
            state.custom.append(CustomNote(seq=entry.seq, name=data.name, data=dict(data.data)))
        case _:
            pass
