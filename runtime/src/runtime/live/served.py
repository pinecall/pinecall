"""A call this gateway serves, and all of them: bound to an app socket, parked, told its commands, counted."""

import asyncio
import contextlib
import logging
import time
from collections.abc import Awaitable, Callable, Generator, Sequence
from dataclasses import dataclass, field

from runtime.actor import Scope
from runtime.agents.declaration import Declaration
from runtime.calls.context import CallContext
from runtime.calls.log import Log
from runtime.calls.models import Opener
from runtime.enums import Env
from runtime.kit.loops import survive
from runtime.live.peers import COMMANDS, RUNNING_CHANNEL, CallsAtOnce, Owners
from runtime.live.pump import pump
from runtime.live.sockets import SocketId, Sockets
from runtime.live.tool_calls import ToolCalls
from runtime.scoping import box_task
from runtime.session import service as session
from runtime.shared_state import SharedState
from runtime.signal import Signal
from runtime.wire.base import Entry
from runtime.wire.signal import Bound, Commanded, RunningShare

logger = logging.getLogger(__name__)

# How often each gateway says which calls each org runs on it.
RUNNING_EVERY_S = 1.0
# How long a call another gateway opened stays served here with no endpoint asking for it.
FIRST_SEEN_IDLE_S = 600.0
# A gateway that said nothing of its calls for this long, five of its beats, is taken for gone: the
# calls it opened are another's to adopt.
OPENER_SILENT_S = 5.0

# What a command heard for a call does to it here: given by whoever builds the calls (`commands.hear`).
type HearCommand = Callable[["Served", Commanded], Awaitable[None]]


@dataclass(frozen=True, slots=True)
class Opening:
    """What serving a call takes: what it is, the declaration it runs on, whose it is, who opened it, its socket."""

    context: CallContext
    declaration: Declaration
    scope: Scope
    # None for a call opened before the head said who.
    opened_by: Opener | None
    # The socket it reaches; None parks it for the next one that takes its agent.
    owner: SocketId | None = None


# A call belongs to its agent, not to a socket: `app` is None while it waits for one. An entity, with
# a life: whoever holds it sees the socket it has now and the session it gained. Until 2026-11 it was
# a frozen value replaced in four places, and whoever kept the copy before went on reading it.
class Served:
    """A call this gateway serves: the socket it reaches, its log, its commands, its tools."""

    def __init__(self, opening: Opening, log: Log, tools: ToolCalls, *, opened_here: bool) -> None:
        self.context = opening.context
        self.declaration = opening.declaration
        # What its log masks by: the declaration it opened on, until a written call's app declares
        # what is private for the call alone (`session.configure`).
        self.masks_by = opening.declaration
        self.scope = opening.scope
        # Who opened it: the worker endpoints of the fleet's call take the fleet's key alone, a
        # written call's take nobody's.
        self.opened_by = opening.opened_by
        # False for a call another gateway opened, served here from what was kept when it opened:
        # it counts on its opener's gateway, and no socket here takes it as parked.
        self.opened_here = opened_here
        self.app = opening.owner
        # A written call runs here; a voice call runs in a worker.
        self.running: session.Session | None = None
        self.log = log
        self.tools = tools
        # Each with the id it was sent under. A None ends the worker's command stream.
        self.commands: asyncio.Queue[Commanded | None] = asyncio.Queue()
        # Held while the call is sealed, so its seal runs once however many times it is asked for.
        self.sealing = asyncio.Lock()
        # Set once the app bound to the call said its end hook ran (call.done): its seal waits for it.
        self.hooked = asyncio.Event()

    @property
    def call(self) -> str:
        """The call's id."""
        return self.context.call

    @property
    def agent(self) -> str:
        """The agent that answers it."""
        return self.declaration.slug


@dataclass(slots=True)
class _Kept:
    """What the calls keep of one of them beside itself: its pump, its listener, when it was seen and parked."""

    served: Served
    heard: asyncio.Event = field(default_factory=asyncio.Event)
    listening: asyncio.Task[None] | None = None
    pump: asyncio.Task[None] | None = None
    # When an endpoint last asked for a call first seen here; None for one opened here.
    seen_at: float | None = None
    # When it lost its socket: a call nobody takes back is ended, not kept for ever.
    parked_at: float | None = None
    # How many streams of its worker read its commands from this gateway now.
    streams: int = 0


# Not durable on purpose: it says which calls are served now; the log is the record. The one writer
# of what it keeps: until 2026-11 nine modules read and wrote its dictionaries from outside.
class Calls:
    """The calls served on this gateway: each one's socket, pump and commands, and every org's count."""

    def __init__(self, signal: Signal, sockets: Sockets, owners: Owners, hear: HearCommand) -> None:
        """Nothing served; what the other gateways run is heard on the signal."""
        self.signal = signal
        self._sockets = sockets
        self._owners = owners
        self._hear = hear
        self._kept: dict[str, _Kept] = {}
        # Since when this gateway hears what the others say they opened.
        self._heard_since = time.monotonic()
        # Each org's calls at once in each env, as every gateway counts its own each second.
        self._counted = SharedState(
            signal,
            RUNNING_CHANNEL,
            load=RunningShare.model_validate,
            dump=_dump_running,
            empty=RunningShare({}),
            on_change=lambda: None,
            every_s=RUNNING_EVERY_S,
            gathered=self._count_here,
        )

    async def start(self) -> None:
        """Hear the other gateways' counts, and say this one's."""
        await self._counted.start()
        self._heard_since = time.monotonic()

    async def close(self) -> None:
        """Stop hearing and saying."""
        await self._counted.close()

    # ── served ──

    # `seen_at` marks a call another gateway opened, served here from what was kept: a cache, let go
    # once idle and read again later.
    def serve(self, served: Served, *, seen_at: float | None = None) -> Served:
        """Serve the call to the socket it names; a call already served stays as it is, and is answered."""
        kept = self._kept.get(served.call)
        if kept is not None:
            return kept.served
        kept = self._kept[served.call] = _Kept(served, seen_at=seen_at)
        self.start_pump(served.call, after=0)
        kept.listening = box_task(self._listen(served.call, kept.heard))
        return served

    def find(self, call: str | None) -> Served | None:
        """The call as this gateway serves it, or None."""
        kept = None if call is None else self._kept.get(call)
        return None if kept is None else kept.served

    def list_served(self) -> list[Served]:
        """Every call served here."""
        return [kept.served for kept in self._kept.values()]

    async def wait_until_heard(self, call: str) -> None:
        """Return once the call's commands are listened for here."""
        kept = self._kept.get(call)
        if kept is not None:
            await kept.heard.wait()

    def run(self, served: Served, running: session.Session) -> None:
        """A written call's session runs here: the other gateways are told so."""
        served.running = running
        self._owners.run_call(served.call, here=True)

    def touch(self, call: str, now: float) -> None:
        """An endpoint asked for a call first seen here: it stays while it is asked for."""
        kept = self._kept.get(call)
        if kept is not None and kept.seen_at is not None:
            kept.seen_at = now

    # ── bound ──

    # Synchronous, so two sockets taking one parked call cannot both have it. The new socket's
    # pump starts once call.attached is written (`handoff.attach`), from it.
    def bind(self, call: str, app: SocketId | None) -> Served | None:
        """Move the call to this socket (None parks it); None when nothing moved."""
        kept = self._kept.get(call)
        if kept is None or kept.served.app == app:
            return None
        self._stop_pump(kept)
        kept.served.app = app
        kept.parked_at = time.monotonic() if app is None else None
        return kept.served

    # What any gateway writes to the call reaches its socket here, in seq order, from `after`;
    # `then` goes down right after the first entry (the tools still waiting, after call.attached).
    def start_pump(self, call: str, *, after: int, then: Sequence[Entry] = ()) -> None:
        """Start sending the call's entries to its socket, if the socket is open here."""
        kept = self._kept.get(call)
        if kept is None or kept.served.app is None:
            return
        socket = self._sockets.find_here(kept.served.app)
        if socket is None:
            self._sockets.tell_bound(kept.served.app, Bound(call=call, after=after))
            return
        self._stop_pump(kept)
        kept.pump = asyncio.ensure_future(pump(kept.served.log, after, socket.send, then))

    def has_pump(self, call: str) -> bool:
        """Whether the call's entries are being sent down a socket open here."""
        kept = self._kept.get(call)
        return kept is not None and kept.pump is not None

    def list_bound_to(self, app: SocketId, agent: str | None = None) -> list[Served]:
        """The calls this socket serves; one agent's, when named."""
        return [
            kept.served for kept in self._kept.values() if kept.served.app == app and agent in (None, kept.served.agent)
        ]

    # ── parked ──

    # Parked by the gateway that opened the call: a copy of it here only follows its opener.
    def list_parked(self) -> list[Served]:
        """The calls this gateway opened that wait for a socket."""
        return [kept.served for kept in self._kept.values() if kept.served.app is None and kept.served.opened_here]

    def list_parked_of(self, scope: Scope, agent: str) -> list[Served]:
        """The calls of the agent in the scope that wait for a socket."""
        return [served for served in self.list_parked() if served.agent == agent and served.scope == scope]

    def list_parked_past(self, now: float, patience_s: float) -> list[Served]:
        """The written calls parked here that no socket took within the patience."""
        return [
            kept.served
            for kept in self._kept.values()
            if kept.parked_at is not None and now - kept.parked_at > patience_s and kept.served.running is not None
        ]

    def forget_parked(self, call: str) -> None:
        """The parked call was ended: it waits for no socket any more."""
        kept = self._kept.get(call)
        if kept is not None:
            kept.parked_at = None

    # ── counted ──

    # The concurrent calls quota counts these, never head rows: a dead worker's row would count
    # for ever. Per env, as every quota is: the sandbox's calls never close production. Every
    # gateway's count, the others' a second old at most, so two gateways admitting at once may go
    # past the limit by what they opened that second.
    # Once each: a call adopted here is still in the share of the gateway that opened it, until that
    # gateway is forgotten.
    def holding(self, org: str, env: Env) -> list[str]:
        """The org's calls open in the env, on every gateway of the box: what its quota of calls at once counts."""
        named = str(CallsAtOnce(org, env))
        theirs = [call for heard in self._counted.theirs.values() for call in heard.share.root.get(named, ())]
        return list(dict.fromkeys([*self._count_here().root.get(named, ()), *theirs]))

    # ── adopted ──

    @contextlib.contextmanager
    def follow(self, call: str) -> Generator[None]:
        """The call's worker reads its commands from this gateway for as long as this is entered."""
        kept = self._kept.get(call)
        if kept is not None:
            kept.streams += 1
        try:
            yield
        finally:
            if kept is not None:
                kept.streams -= 1

    # A spoken call outlives the gateway that opened it: its worker goes on and reads its commands from
    # another, which held it as a copy alone. So no socket that took its agent was handed it, its tools
    # waited out their deadline, and once its opener was forgotten it counted against nobody. The gateway
    # its worker reads from adopts it: it counts here, and parks and is handed on from here. Two gateways
    # that adopted one call, each deaf to the other for a moment, settle it when they hear each other: the
    # one of the greater id leaves it and serves a copy again.
    def adopt_orphans(self, now: float) -> list[Served]:
        """Take as opened here the calls whose opener is gone and whose worker reads here, and say so; which."""
        if now - self._heard_since < OPENER_SILENT_S:
            return []
        elsewhere = self._find_opened_elsewhere(now)
        mine = self._counted.id
        adopted: list[Served] = []
        left = False
        for kept in self._kept.values():
            served = kept.served
            if served.opened_here and served.running is None and elsewhere.get(served.call, mine) < mine:
                served.opened_here, kept.seen_at, left = False, now, True
            elif not served.opened_here and kept.streams and served.call not in elsewhere:
                served.opened_here, kept.seen_at = True, None
                adopted.append(served)
        if adopted or left:
            self._counted.put(self._count_here())
        return adopted

    # ── let go ──

    # A call first seen here is a cache of what was kept: let go when idle, and read again later.
    def let_idle_go(self, now: float) -> None:
        """Let go of the calls first seen here that no endpoint asked for in FIRST_SEEN_IDLE_S."""
        idle = [
            call
            for call, kept in self._kept.items()
            if kept.seen_at is not None and now - kept.seen_at > FIRST_SEEN_IDLE_S and kept.pump is None
        ]
        for call in idle:
            self.close_call(call)

    def close_call(self, call: str) -> None:
        """Forget a finished call: its entries end, and its worker's command stream."""
        kept = self._kept.pop(call, None)
        if kept is None:
            return
        self._stop_pump(kept)
        kept.served.commands.put_nowait(None)
        self._owners.run_call(call, here=False)
        if kept.listening is not None:
            kept.listening.cancel()

    # ── private ──

    # A voice call's commands wait here for its worker's stream; a written call's session takes
    # them at once. Heard whichever gateway the app or the desk sent them to. A command that could
    # not be applied is said with its call and the next is heard: a listener that ended on it would
    # lose every command after it in silence.
    async def _listen(self, call: str, heard: asyncio.Event) -> None:
        async def take(said: Commanded) -> None:
            kept = self._kept.get(call)
            if kept is not None and kept.served.agent == said.command.agent:
                with survive("a command of the call", call):
                    await self._hear(kept.served, said)

        await COMMANDS.listen(self.signal, take, asked=heard, call=call)

    # A gateway that said nothing for OPENER_SILENT_S is not among them: it beats every second.
    def _find_opened_elsewhere(self, now: float) -> dict[str, str]:
        return {
            call: gateway
            for gateway, heard in self._counted.theirs.items()
            if now - heard.at <= OPENER_SILENT_S
            for calls in heard.share.root.values()
            for call in calls
        }

    def _count_here(self) -> RunningShare:
        open_here: dict[str, list[str]] = {}
        for kept in self._kept.values():
            if kept.served.opened_here:
                named = str(CallsAtOnce(kept.served.scope.org, kept.served.scope.env))
                open_here.setdefault(named, []).append(kept.served.call)
        return RunningShare(open_here)

    def _stop_pump(self, kept: _Kept) -> None:
        if kept.pump is not None:
            kept.pump.cancel()
            kept.pump = None


def _dump_running(share: RunningShare) -> object:
    return share.model_dump(mode="json")
