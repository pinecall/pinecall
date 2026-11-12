"""A call's commands: what each one of the app's and of a supervisor does to it, the gateway's signals, the refusal."""

import logging
from collections.abc import Awaitable, Callable
from typing import assert_never

from runtime.exceptions import Conflict, PinecallError, ValidationError
from runtime.session import prompt
from runtime.session.session import Session
from runtime.wire import events as wire
from runtime.wire.base import Command
from runtime.wire.commands import (
    AgentReply,
    AgentSay,
    CallAttention,
    CallCallback,
    CallDone,
    CallDtmf,
    CallerHungUp,
    CallEvent,
    CallHangup,
    CallHold,
    CallLog,
    CallMute,
    CallTransfer,
    CallUnhold,
    CallUnmute,
    EndVerb,
    ParticipantMute,
    ParticipantRemove,
    PromptSet,
    ReleaseVerb,
    RoomInvite,
    RoomSend,
    SayVerb,
    SessionConfigure,
    StagesChanged,
    StateSet,
    SupervisorVerb,
    TakeoverVerb,
    ToolsSet,
    TransferVerb,
    WhisperVerb,
    command_of,
    signal_of,
)

logger = logging.getLogger(__name__)

# The commands that act on a running call. The rest of the wire's are the gateway's own (an agent
# registered, a tool answered, a call dialled or claimed) and never reach a session.
type CallCommand = (
    AgentReply
    | AgentSay
    | CallAttention
    | CallCallback
    | CallDone
    | CallDtmf
    | CallEvent
    | CallHangup
    | CallHold
    | CallLog
    | CallMute
    | CallTransfer
    | CallUnhold
    | CallUnmute
    | ParticipantMute
    | ParticipantRemove
    | PromptSet
    | RoomInvite
    | RoomSend
    | SessionConfigure
    | StateSet
    | SupervisorVerb
    | ToolsSet
)
OF_A_CALL = (
    AgentReply,
    AgentSay,
    CallAttention,
    CallCallback,
    CallDone,
    CallDtmf,
    CallEvent,
    CallHangup,
    CallHold,
    CallLog,
    CallMute,
    CallTransfer,
    CallUnhold,
    CallUnmute,
    ParticipantMute,
    ParticipantRemove,
    PromptSet,
    RoomInvite,
    RoomSend,
    SessionConfigure,
    StateSet,
    SupervisorVerb,
    ToolsSet,
)
# Takes the call's stages anew, as its agent's settings name them now or as the agent named does:
# given by a host that can (a worker's job), None by one that cannot (the gateway).
type Restage = Callable[[str | None], Awaitable[None]]

# `error` entry codes for a command the call did not take: its shape, or what it asked.
BAD_SHAPE = "bad_shape"
REFUSED = "refused"
NOT_A_CALLS = "{command} is not a command of a running call"
RUN_BY_THE_GATEWAY = "a written call the gateway runs keeps the model it opened on: its settings run on the next one"


# One table: a command is decoded once and each arm is one call to whoever owns what it changes (the
# call, the line, the room, the session's own life). Closed over the union, so a command the wire
# gains fails the type check here until it has an arm: until 2026-11 four ladders each answered
# "not mine", and `call.mute` reached production with no handler.
async def apply(session: Session, command: CallCommand) -> None:
    """What one command of the app does to this call."""
    call, line = session.call, session.line
    match command:
        case PromptSet():
            await session.set_prompt(command.name, command.text)
        case ToolsSet():
            await call.set_tools(command)
        case StateSet():
            await session.set_state(command)
        case CallEvent():
            await call.receive(command.name, command.data, source="app")
        case CallLog():
            await call.log_custom(command)
        case CallDone():
            await call.app_finished()
        case CallCallback():
            await call.call_back(command)
        case SessionConfigure():
            await call.configure(command)
        case AgentSay():
            session.say(command)
        case AgentReply():
            session.reply(command)
        case CallHangup():
            session.hang_up("agent_hung_up")
        case CallHold():
            await line.hold()
        case CallUnhold():
            await line.unhold()
        case CallAttention():
            await line.await_a_person(command)
        case CallTransfer():
            await session.transfer(command)
        case SupervisorVerb():
            await supervise(session, command)
        case (
            RoomInvite() | RoomSend() | ParticipantMute() | ParticipantRemove() | CallDtmf() | CallMute() | CallUnmute()
        ):
            await session.room_or_refuse(command).apply(command)
        case _:
            assert_never(command)


async def supervise(session: Session, command: SupervisorVerb) -> None:
    """One of a supervisor's six verbs, written before it acts."""
    by, verb, writing = command.by, command.verb, session.call.writing
    match verb:
        case SayVerb():
            await writing.write("supervisor.said", wire.SupervisorSaid(by=by, text=verb.text))
            session.live.say(verb.text, allow_interruptions=True)
        case WhisperVerb():
            await writing.write("supervisor.whispered", wire.SupervisorWhispered(by=by, text=verb.text))
            note = prompt.A_WHISPER.format(text=verb.text)
            await session.note(note)
            if session.line.agent_may_speak:
                session.live.generate_reply(instructions=note)
        case TakeoverVerb():
            await session.line.take(by)
        case ReleaseVerb():
            await session.line.release(by)
            await session.note(prompt.A_RELEASE)
            if session.line.agent_may_speak:
                session.live.generate_reply(instructions=prompt.A_RELEASE)
        case EndVerb():
            await writing.write("supervisor.ended", wire.SupervisorEnded(by=by, reason=verb.reason))
            session.hang_up("supervisor_ended", "supervisor", at_once=True)
        case TransferVerb():
            await session.transfer(CallTransfer(to=verb.to, mode=verb.mode), by=by)
        case _:
            assert_never(verb)


# The envelope a call's command stream is read with, the same in the gateway and in a worker: one of
# the gateway's own signals, or a command of the app's. The refusal is answered, not written: each
# host writes it where it writes (the call's log itself, or the call's writer). Until 2026-11 it was
# built in four places, and a worker said `refused` for what the gateway called `bad_shape`.
async def take(session: Session, command: Command, *, restage: Restage | None = None) -> wire.ErrorEvent | None:
    """Take one command off a call's stream; the `error` entry of one the call refused, else None."""
    try:
        match signal_of(command):
            case CallerHungUp():
                session.caller_hung_up()
            case StagesChanged(agent=agent):
                if restage is None:
                    raise Conflict(RUN_BY_THE_GATEWAY)
                await restage(agent)
            case None:
                await apply(session, command_of_a_call(command))
    except PinecallError as refused:
        logger.warning("call %s: %s refused: %s", session.call.context.call, command.type, refused)
        return refusal_of(command, refused)
    return None


def command_of_a_call(command: Command) -> CallCommand:
    """The command's data as the model its type names; one that is not a running call's is refused."""
    model = command_of(command)
    if not isinstance(model, OF_A_CALL):
        raise ValidationError(NOT_A_CALLS.format(command=command.type))
    return model


def refusal_of(command: Command, refused: PinecallError) -> wire.ErrorEvent:
    """The one `error` entry for a command a call refused: its shape, or what it asked."""
    code = BAD_SHAPE if isinstance(refused, ValidationError) else REFUSED
    return wire.ErrorEvent(code=code, message=str(refused), command=command.type, id=command.id, recoverable=True)
