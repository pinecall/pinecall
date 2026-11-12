"""A command for a live call: handed to whatever runs it, here or on another gateway, its refusal said one way."""

from dataclasses import dataclass
from uuid import uuid4

from runtime.actor import Scope
from runtime.agents import service as agents
from runtime.exceptions import Conflict, NotFound, PinecallError, ValidationError
from runtime.kit.text import JsonObject
from runtime.live.parts import LiveParts
from runtime.live.peers import COMMANDS
from runtime.live.served import Calls, Served
from runtime.live.sockets import Sockets
from runtime.session import service as session
from runtime.signal import Signal
from runtime.wire.base import Command, Entry
from runtime.wire.commands import SessionConfigure
from runtime.wire.events import ErrorEvent
from runtime.wire.signal import Commanded

# The gateway's own words to whatever runs a call (`wire.commands`): the one verb a desk sends, which a
# call takes as a supervisor's; the caller's own hang-up, said at the gateway; the call taking its
# stages anew. None is an app's to say: an app's socket refuses each.
SUPERVISOR_VERB = "supervisor.verb"
CALLER_HUNG_UP = "caller.hung_up"
STAGES_CHANGED = "stages.changed"
SESSION_CONFIGURE = "session.configure"
# How a refused command is said, on the call's log and down a socket.
BAD_SHAPE = "bad_shape"
REFUSED = "refused"


@dataclass(frozen=True, slots=True)
class Restaging:
    """A live call asked to take its stages anew: in whose scope, and the teammate whose stages it takes."""

    call: str
    scope: Scope
    passed_to: str | None = None


@dataclass(frozen=True, slots=True)
class Delivery:
    """What came of a command: whether anything runs its call, and the refusal of the call that runs here."""

    reached: bool
    refusal: ErrorEvent | None = None


# One dispatcher. Until 2026-11 a command reached a session by two (the socket's own shortcut, and what
# was heard on the call's channel) and a supervisor's verb by two more, and which one ran depended on
# the gateway the request landed on: the same refusal was an HTTP error with nothing on the log, or a
# 200 with an `error` entry and a frame to the app. Now a call that runs here takes the command here,
# and one that does not is told on its channel; a refusal is an `error` entry on the call's log, always,
# and it is answered to whoever sent the command when this gateway is the one that heard them.
async def deliver(calls: Calls, signal: Signal, command: Command) -> Delivery:
    """Hand a command to whatever runs its call: the session here, else the gateways that serve it."""
    served = calls.find(command.call)
    if served is not None and served.agent == command.agent and served.running is not None:
        return Delivery(reached=True, refusal=await take_here(served, served.running, command))
    if command.call is None:
        return Delivery(reached=False)
    # Whichever gateway runs the call's worker stream or its session takes it.
    said = Commanded(id=uuid4().hex, command=command)
    return Delivery(reached=await COMMANDS.reach(signal, said, call=command.call))


# A verb the call cannot take is said on the call's log, as a worker says it on a spoken call: the
# app hears it on its socket, a person reads it on the call's log.
async def take_here(served: Served, running: session.Session, command: Command) -> ErrorEvent | None:
    """Apply the command to the session that runs here; the refusal, written on the call's log, when it refuses."""
    declare_for_the_call(served, command)
    refusal = await session.take(running, command)
    if refusal is not None:
        await served.log.append("error", refusal.dump())
    return refusal


# What the call's channel says, whichever gateway the app or the desk sent it to: a voice call's
# commands wait here for its worker's stream; a written call's session takes them at once. The sender
# is on another gateway, which answered it already: the refusal is on the call's log, and told to the
# socket the call is bound to, which is the app that sent it when an app did.
async def hear(sockets: Sockets, served: Served, said: Commanded) -> None:
    """One command heard for a call served here: queued for its worker, or taken by its session."""
    if served.running is None:
        served.commands.put_nowait(said)
        return
    command = said.command
    refusal = await take_here(served, served.running, command)
    if refusal is not None and served.app is not None:
        await sockets.tell(served.app, Entry.make_unstored(command.agent, "error", refusal.dump()))


def declare_for_the_call(served: Served, command: Command) -> None:
    """A written call's own declaration of what is private, as the app configured it for the call."""
    if command.type != SESSION_CONFIGURE:
        return
    try:
        wanted = SessionConfigure.parse(command.data, command.type)
    except ValidationError:
        # The session refuses the same body a moment later, and says why.
        return
    if wanted.config is not None:
        served.masks_by = agents.apply_declaration(served.masks_by, wanted.config)
        served.log.privacy.declare(served.masks_by)


def refusal_error(refusal: ErrorEvent) -> PinecallError:
    """The refusal of a command as the error a request is answered with: its shape, or what it asked."""
    return ValidationError(refusal.message) if refusal.code == BAD_SHAPE else Conflict(refusal.message)


# ── the gateway's own three ──


# The body never says who sent it: the credential does. One preamble for the three: until 2026-11
# each emitter wrote it again (a call nobody wrote is a 404, a sealed one a 409, nobody serving it a 404).
async def send_to_live_call(live: LiveParts, call: str, kind: str, data: JsonObject) -> None:
    """One of the gateway's own commands to a live call; refused when the call is unknown, over, or refuses it."""
    state = await live.logs.reading(call).snapshot()
    if state.seq == 0:
        raise NotFound(f"no call {call} in this key's org and env")
    if await live.store.is_sealed(call):
        raise Conflict(f"call {call} is over: read its log or its recording instead")
    delivered = await deliver(live.calls, live.signal, Command(type=kind, agent=state.agent, call=call, data=data))
    if delivered.refusal is not None:
        raise refusal_error(delivered.refusal)
    if not delivered.reached:
        raise NotFound(f"no call {call} in this key's org and env")


# A hang-up said on the room's data channel is lost when the page leaves the room the same instant,
# and the call then waits for a caller who is not coming back. Said here, it reaches the call.
async def hang_up_for_caller(live: LiveParts, call: str) -> None:
    """The caller hung up: whatever runs the call ends it now, as the caller's own hang-up."""
    await send_to_live_call(live, call, CALLER_HUNG_UP, {})


# Only a call a worker runs follows it: a written call the gateway runs itself keeps the model it opened on.
async def restage(live: LiveParts, scope: Scope, call: str, passed_to: str | None = None) -> None:
    """The live call takes its model and its voice as its agent's settings name them now, or as `passed_to`'s do."""
    if passed_to is not None and live.holders.find_serving(scope, passed_to) is None:
        raise NotFound(f"nobody holds {passed_to} here: a call takes the stages of an agent an app is serving")
    await send_to_live_call(live, call, STAGES_CHANGED, {"agent": passed_to} if passed_to else {})
