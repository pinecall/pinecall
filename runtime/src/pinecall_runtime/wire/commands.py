"""Every command an app sends, the supervise verbs, and the registry of them."""

from typing import Annotated, Any, Literal

from pydantic import Field

from pinecall_runtime.exceptions import ValidationError
from pinecall_runtime.wire.base import Command, WireModel
from pinecall_runtime.wire.parts import (
    AgentConfig,
    Contact,
    Route,
    StateCause,
    Supervisor,
    ToolResult,
    ToolSpec,
    TransferMode,
)

# Which events a command lands in the log as, so a caller knows what to wait for.
PRODUCES: dict[str, tuple[str, ...]] = {
    "agent.configure": ("agent.configured",),
    "agent.drain": ("agent.draining",),
    "agent.register": ("agent.registered",),
    "agent.reply": ("turn.agent",),
    "agent.say": ("turn.agent",),
    "call.attention": ("attention.requested", "call.line", "attention.answered"),
    "call.callback": ("callback.requested",),
    "call.claim": ("call.claimed",),
    "call.dial": ("call.dialing",),
    "call.done": (),
    "call.dtmf": (),
    "call.opt_out": (),
    "call.event": ("event.received",),
    "call.hangup": ("call.ended",),
    "call.hold": ("call.line",),
    "call.log": ("custom",),
    "call.mute": ("call.line",),
    "call.transfer": ("call.transferred",),
    "call.unhold": ("call.line",),
    "call.unmute": ("call.line",),
    "dev.answer": (),
    "participant.mute": ("track.unpublished",),
    "participant.remove": ("participant.left",),
    "ping": ("pong",),
    "prompt.set": ("prompt.changed",),
    "room.invite": ("participant.joined",),
    "room.send": ("room.sent",),
    "session.configure": ("state.changed", "agent.configured"),
    "state.set": ("state.changed",),
    "supervisor.verb": (
        "supervisor.said",
        "supervisor.whispered",
        "supervisor.took_over",
        "supervisor.released",
        "supervisor.transferred",
        "supervisor.ended",
    ),
    "tool.result": ("tool.result",),
    "tools.set": ("tools.changed",),
}


class SayVerb(WireModel):
    """Make the agent say this, verbatim."""

    verb: Literal["say"] = "say"
    text: str


class WhisperVerb(WireModel):
    """Tell the agent something the caller never hears."""

    verb: Literal["whisper"] = "whisper"
    text: str


class TakeoverVerb(WireModel):
    """The supervisor takes the line."""

    verb: Literal["takeover"] = "takeover"


class ReleaseVerb(WireModel):
    """The supervisor hands the line back."""

    verb: Literal["release"] = "release"


class TransferVerb(WireModel):
    """Send the caller to another number."""

    verb: Literal["transfer"] = "transfer"
    to: str
    mode: TransferMode | None = None


class EndVerb(WireModel):
    """Hang up on the caller's behalf."""

    verb: Literal["end"] = "end"
    reason: str | None = None


type Verb = Annotated[
    SayVerb | WhisperVerb | TakeoverVerb | ReleaseVerb | TransferVerb | EndVerb,
    Field(discriminator="verb"),
]


class AgentConfigure(WireModel):
    """Declare or change what the agent is; only the fields sent change."""

    config: AgentConfig


class AgentDrain(WireModel):
    """This socket is leaving, and its calls go on without it."""


class AgentRegister(WireModel):
    """The app's first message: this socket speaks for this agent and answers these routes."""

    routes: list[Route]
    sdk: str | None = None
    host: str | None = None
    takes_unclaimed: bool = True
    answers_dev: bool = False
    says_done: bool = False


class AgentReply(WireModel):
    """Make the model speak now, guided by an instruction the caller never hears."""

    instructions: str
    allow_interruptions: bool | None = None


class AgentSay(WireModel):
    """Make the agent say this text now, verbatim."""

    text: str
    allow_interruptions: bool | None = None


class CallAttention(WireModel):
    """Ask for a person without sending the caller anywhere; fifteen minutes at most."""

    reason: str
    wait_s: float = Field(gt=0, le=900)


class CallCallback(WireModel):
    """Write down that the caller wants to be called back."""

    number: str
    when: str | None = None
    note: str | None = None


class CallClaim(WireModel):
    """The code the caller said, to bind this call to the page that shows it."""

    code: str = Field(pattern="^[0-9]{4}$")


class CallDial(WireModel):
    """Place an outbound call as this agent."""

    to: str
    from_: str | None = Field(None, alias="from")
    caller: Contact | None = None
    metadata: dict[str, Any] | None = None


class CallOptOut(WireModel):
    """The caller asked never to be called again."""

    note: str | None = Field(default=None, max_length=500)


class CallDtmf(WireModel):
    """Send touch tones down the line."""

    digits: str


class CallEvent(WireModel):
    """Hand the agent a fact from the tenant's backend."""

    name: str
    data: dict[str, Any]


class CallDone(WireModel):
    """The app's end hook ran and everything it wrote was sent: the call may be sealed."""


class CallHangup(WireModel):
    """End the call from the app's side."""

    reason: str | None = None


class CallHold(WireModel):
    """Put the caller on hold."""


class CallLog(WireModel):
    """Write a line of the app's own into the call's log."""

    name: str
    data: dict[str, Any]


class CallMute(WireModel):
    """Mute the agent."""


class CallTransfer(WireModel):
    """Send the caller to another number, or bring that number into the call."""

    to: str
    mode: TransferMode | None = None


class CallUnhold(WireModel):
    """Take the caller off hold."""


class CallUnmute(WireModel):
    """Unmute the agent."""


class DevRefusal(WireModel):
    """Why the verb did not run."""

    status: int
    detail: str


class DevAnswer(WireModel):
    """What came of one dev.request."""

    id: str
    result: dict[str, Any] | None = None
    refused: DevRefusal | None = None


class ParticipantMute(WireModel):
    """Silence a participant for the rest of the call."""

    identity: str


class ParticipantRemove(WireModel):
    """Put a participant out of the room; removing the caller ends the call."""

    identity: str


class Ping(WireModel):
    """Is the socket alive?"""


class PromptSet(WireModel):
    """Rewrite one block of the prompt, whole, by name."""

    name: str
    text: str


class RoomInvite(WireModel):
    """Bring somebody else into the call's room."""

    to: str
    kind: Literal["sip", "participant"]


class RoomSend(WireModel):
    """Push a payload to a browser in the room."""

    topic: str
    data: dict[str, Any]
    to: str | None = None


class SessionConfigure(WireModel):
    """Set up this one call before the first turn."""

    state: dict[str, Any] | None = None
    config: AgentConfig | None = None


class StateSet(WireModel):
    """The app's state changed and this is all of it."""

    state: dict[str, Any]
    changed: list[str] | None = None
    cause: StateCause | None = None


class SupervisorVerb(WireModel):
    """One supervise verb, from the human the endpoint named."""

    by: Supervisor
    verb: Verb


class ToolsSet(WireModel):
    """The tools the model may see now."""

    tools: list[ToolSpec]


COMMANDS: dict[str, type[WireModel]] = {
    "agent.configure": AgentConfigure,
    "agent.drain": AgentDrain,
    "agent.register": AgentRegister,
    "agent.reply": AgentReply,
    "agent.say": AgentSay,
    "call.attention": CallAttention,
    "call.callback": CallCallback,
    "call.claim": CallClaim,
    "call.dial": CallDial,
    "call.done": CallDone,
    "call.dtmf": CallDtmf,
    "call.opt_out": CallOptOut,
    "call.event": CallEvent,
    "call.hangup": CallHangup,
    "call.hold": CallHold,
    "call.log": CallLog,
    "call.mute": CallMute,
    "call.transfer": CallTransfer,
    "call.unhold": CallUnhold,
    "call.unmute": CallUnmute,
    "dev.answer": DevAnswer,
    "participant.mute": ParticipantMute,
    "participant.remove": ParticipantRemove,
    "ping": Ping,
    "prompt.set": PromptSet,
    "room.invite": RoomInvite,
    "room.send": RoomSend,
    "session.configure": SessionConfigure,
    "state.set": StateSet,
    "supervisor.verb": SupervisorVerb,
    "tool.result": ToolResult,
    "tools.set": ToolsSet,
}


def said_as(command: WireModel) -> str:
    """The command as the wire names it: `call.mute`, or a supervisor's verb as `supervise <verb>`."""
    verb = getattr(command, "verb", None)
    if isinstance(verb, str):
        return f"supervise {verb}"
    return next((name for name, model in COMMANDS.items() if isinstance(command, model)), type(command).__name__)


def command_of(command: Command) -> WireModel:
    """The command's data as the model its type names; an unknown type is refused."""
    model = COMMANDS.get(command.type)
    if model is None:
        raise ValidationError(f"unknown command type: {command.type}")
    return model.parse(command.data, command.type)
