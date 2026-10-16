"""The calls this gateway serves: handed to an app socket, parked, told their commands, counted."""

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass, field, replace

from pydantic import TypeAdapter

from pinecall_runtime.agents.declaration import AgentConfig
from pinecall_runtime.agents.service import declared, registry
from pinecall_runtime.calls.context import CallContext
from pinecall_runtime.calls.logs import Log
from pinecall_runtime.calls.service.peers import (
    ANSWER_CHANNEL,
    APP_CHANNEL,
    COMMANDS_CHANNEL,
    SUPERVISOR_VERB,
    Elsewhere,
    Owners,
    SocketRow,
    answer_back,
    tell_app,
    tell_bound,
)
from pinecall_runtime.calls.service.pump import Send, pump
from pinecall_runtime.calls.service.tool_calls import ToolCalls
from pinecall_runtime.enums import Env, Opener
from pinecall_runtime.exceptions import ServiceUnavailable
from pinecall_runtime.kit.auth import Scope
from pinecall_runtime.kit.shared_state import SharedState
from pinecall_runtime.redis import Listener, LocalSignal, Signal
from pinecall_runtime.session import service as session
from pinecall_runtime.wire.base import Command, Entry, WireModel
from pinecall_runtime.wire.commands import DevAnswer, SessionConfigure, SupervisorVerb, command_of
from pinecall_runtime.wire.signal import Bound, ForApp

logger = logging.getLogger(__name__)

# Where each gateway says how many calls each org runs on it, and how often.
RUNNING_CHANNEL = "running"
RUNNING_EVERY_S = 1.0
_RUNNING: TypeAdapter[dict[str, int]] = TypeAdapter(dict[str, int])

# How long a call another gateway opened stays served here with no endpoint asking for it.
FIRST_SEEN_IDLE_S = 600.0


# A call belongs to its agent, not to a socket: `app` is None while it waits for one.
@dataclass(frozen=True)
class Served:
    """A call this gateway serves: the socket it reaches, its log, its commands, its tools."""

    agent: str
    scope: Scope
    app: registry.SocketId | None
    log: Log
    # A None ends the worker's command stream.
    commands: asyncio.Queue[Command | None]
    context: CallContext
    config: AgentConfig
    tools: ToolCalls
    # A written call runs here; a voice call runs in a worker.
    running: session.Session | None = None
    # Held while the call is sealed, so its seal runs once however many times it is asked for.
    sealing: asyncio.Lock = field(default_factory=asyncio.Lock)
    # False for a call another gateway opened, served here from what was kept when it opened:
    # it counts on its opener's gateway, and no socket here takes it as parked.
    opened_here: bool = True
    # Who opened it: the worker endpoints of the fleet's call take the fleet's key alone, a
    # written call's take nobody's. None for a call opened before the head said.
    opened_by: Opener | None = None

    @property
    def call(self) -> str:
        """The call's id."""
        return self.context.call


# Not durable on purpose: it says which sockets are open now; the log is the record.
class Live:
    """The open app sockets and the calls served to them."""

    def __init__(self, signal: Signal | None = None) -> None:
        """Nothing open; bindings to other gateways' sockets told on the signal."""
        self.signal = signal or LocalSignal()
        # Which written calls and threads run here, and on the other gateways; their sockets.
        self.owners = Owners(self.signal)
        self.elsewhere = Elsewhere(self.signal)
        # Each org's calls at once in each env, as every gateway counts its own each second.
        self.counted = SharedState(self.signal, RUNNING_CHANNEL, _RUNNING, {}, lambda: None)
        self.counted.every_s = RUNNING_EVERY_S
        self.counted.gathered = self._running_here
        # Each dev.request asked here, listening for its answer from the socket's gateway.
        self.answers: dict[str, asyncio.Task[None]] = {}
        self.sockets: dict[registry.SocketId, Send] = {}
        self.apps: dict[registry.SocketId, registry.ConnectedApp] = {}
        self.calls: dict[str, Served] = {}
        # The calls first seen here, by when an endpoint last asked for one: let go once idle.
        self.seen: dict[str, float] = {}
        # When each parked call lost its socket: a call nobody takes back is ended, not kept for ever.
        self.parked_since: dict[str, float] = {}
        self.pending_answers: dict[str, asyncio.Future[DevAnswer]] = {}
        # Each bound call's pump to its socket, and each call's listener for its commands, by
        # call: held here, since asyncio keeps weak references to tasks, and cancelled at the end.
        self.pumps: dict[str, asyncio.Task[None]] = {}
        self.listening: dict[str, tuple[asyncio.Event, asyncio.Task[None]]] = {}

    async def start(self) -> None:
        """Hear the other gateways' owners and sockets, and say this one's."""
        await self.owners.start()
        await self.elsewhere.start()
        await self.counted.start()

    async def close(self) -> None:
        """Stop hearing and saying."""
        await self.owners.close()
        await self.elsewhere.close()
        await self.counted.close()

    # ── the sockets ──

    def connect(self, app: registry.ConnectedApp, send: Send) -> None:
        """An app socket opened."""
        self.sockets[app.app] = send
        self.apps[app.app] = app
        self._say_sockets()

    def disconnect(self, app: registry.SocketId) -> None:
        """An app socket closed; its calls go on until another socket takes them."""
        self.sockets.pop(app, None)
        self.apps.pop(app, None)
        self._say_sockets()

    def named(self, app: registry.SocketId, host: str | None) -> None:
        """The machine the app said it runs on."""
        found = self.apps.get(app)
        if found is not None and host is not None:
            self.apps[app] = replace(found, host=host)
            self._say_sockets()

    # The other gateways' sockets are stopped through their inbox, as any message to them is.
    def apps_of(self, org: str, env: Env) -> list[registry.ConnectedApp]:
        """The org's sockets in the env on every gateway, oldest first."""
        mine = [app for app in self.apps.values() if app.scope.org == org and app.scope.env == env]
        theirs = [
            registry.ConnectedApp(row.app, row.scope, row.address, row.connected_at, self._stop(row.app), row.host)
            for row in self.elsewhere.rows_of(org, env.value)
        ]
        return sorted([*mine, *theirs], key=lambda one: one.connected_at)

    async def inbox(self, app: registry.SocketId) -> Listener:
        """The socket's inbox on the signal: what other gateways send it, while it is open here."""
        return await self.signal.subscribe(APP_CHANNEL.format(app=app))

    # dev.request is never stored: it goes straight down the socket, wherever it is held.
    async def tell(self, app: registry.SocketId, entry: Entry) -> bool:
        """Send an entry to one socket; False when no gateway holds it."""
        send = self.sockets.get(app)
        if send is None:
            return await tell_app(self.signal, app, ForApp(entry=entry))
        await send(entry)
        return True

    async def ask(self, ask_id: str) -> asyncio.Future[DevAnswer]:
        """A future for the answer to a dev.request, answered here or by the socket's gateway."""
        answer: asyncio.Future[DevAnswer] = asyncio.get_running_loop().create_future()
        self.pending_answers[ask_id] = answer
        heard = asyncio.Event()
        task = asyncio.create_task(self._answer_from_there(ask_id, answer, heard))
        self.answers[ask_id] = task

        # Answered, or given up on (the asker cancels it): the listener goes with it.
        def over(_: asyncio.Future[DevAnswer]) -> None:
            self.answers.pop(ask_id, None)
            task.cancel()

        answer.add_done_callback(over)
        await heard.wait()
        return answer

    async def dev_answered(self, answer: DevAnswer) -> bool:
        """Hand an app's dev.answer to the endpoint waiting for it; False when nobody waits."""
        waiting = self.pending_answers.pop(answer.id, None)
        if waiting is None:
            return await answer_back(self.signal, answer)
        if waiting.done():
            return False
        waiting.set_result(answer)
        return True

    # ── the calls ──

    def serve(self, served: Served) -> None:
        """Serve the call to the socket its endpoint chose; a call already served stays as it is."""
        if served.call in self.calls:
            return
        self.calls[served.call] = served
        self.pumped(served.call, after=0)
        heard = asyncio.Event()
        self.listening[served.call] = (heard, asyncio.create_task(self._commands(served.call, heard)))

    async def commands_heard(self, call: str) -> None:
        """Return once the call's commands are listened for here."""
        listening = self.listening.get(call)
        if listening is not None:
            await listening[0].wait()

    # Synchronous, so two sockets taking one parked call cannot both have it. The new socket's
    # pump starts once call.attached is written (binding.attach), from it.
    def attach(self, call: str, app: registry.SocketId | None) -> Served | None:
        """Move the call to this socket (None parks it); None when nothing moved."""
        served = self.calls.get(call)
        if served is None or served.app == app:
            return None
        self._stop_pump(call)
        moved = replace(served, app=app)
        self.calls[call] = moved
        if app is None:
            self.parked_since[call] = time.monotonic()
        else:
            self.parked_since.pop(call, None)
        return moved

    def parked_past(self, now: float, patience_s: float) -> list[Served]:
        """The written calls parked here that no socket took within the patience."""
        return [
            self.calls[call]
            for call, since in self.parked_since.items()
            if now - since > patience_s and call in self.calls and self.calls[call].running is not None
        ]

    # What any gateway writes to the call reaches its socket here, in seq order, from `after`;
    # `then` goes down right after the first entry (the tools still waiting, after call.attached).
    def pumped(self, call: str, *, after: int, then: Sequence[Entry] = ()) -> None:
        """Start sending the call's entries to its socket, if the socket is open here."""
        served = self.calls.get(call)
        if served is None or served.app is None:
            return
        send = self.sockets.get(served.app)
        if send is None:
            tell_bound(self.signal, served.app, Bound(call=call, after=after))
            return
        self._stop_pump(call)
        self.pumps[call] = asyncio.ensure_future(pump(served.log, after, send, then))

    def set_opener(self, call: str, opener: Opener | None) -> None:
        """Say who opened the call, once it is served here."""
        served = self.calls.get(call)
        if served is not None:
            self.calls[call] = replace(served, opened_by=opener)

    def set_session(self, call: str, running: session.Session) -> Served:
        """A written call's session runs here."""
        served = replace(self.calls[call], running=running)
        self.calls[call] = served
        self.owners.running(call, here=True)
        return served

    def bound_to(self, app: registry.SocketId) -> list[str]:
        """The calls this socket serves."""
        return [call for call, served in self.calls.items() if served.app == app]

    def parked(self, scope: Scope, agent: str) -> list[str]:
        """The calls of the agent in the scope that wait for a socket."""
        return [
            call
            for call, served in self.calls.items()
            if served.app is None and served.opened_here and served.agent == agent and served.scope == scope
        ]

    # The concurrent calls quota counts these, never head rows: a dead worker's row would count
    # for ever. Per env, as every quota is: the sandbox's calls never close production. Every
    # gateway's count, the others' a second old at most, so two gateways admitting at once may go
    # past the limit by what they opened that second.
    def running(self, org: str, env: Env) -> int:
        """How many of the org's calls are open in the env, on every gateway of the box."""
        named = f"{org}|{env.value}"
        theirs = sum(heard.share.get(named, 0) for heard in self.counted.theirs.values())
        return self._running_here().get(named, 0) + theirs

    def in_use(self, call: str, now: float) -> None:
        """An endpoint asked for a call first seen here: it stays while it is asked for."""
        if call in self.seen:
            self.seen[call] = now

    # A call first seen here is a cache of what was kept: let go when idle, and read again later.
    def let_idle_go(self, now: float) -> None:
        """Let go of the calls first seen here that no endpoint asked for in FIRST_SEEN_IDLE_S."""
        idle = [call for call, at in self.seen.items() if now - at > FIRST_SEEN_IDLE_S]
        for call in idle:
            if call not in self.pumps:
                self.close_call(call)

    def close_call(self, call: str) -> None:
        """Forget a finished call: its entries end, and its worker's command stream."""
        self.seen.pop(call, None)
        self.parked_since.pop(call, None)
        served = self.calls.pop(call, None)
        if served is None:
            return
        self._stop_pump(call)
        served.commands.put_nowait(None)
        self.owners.running(call, here=False)
        listening = self.listening.pop(call, None)
        if listening is not None:
            listening[1].cancel()

    # ── private ──

    # A voice call's commands wait here for its worker's stream; a written call's session takes
    # them at once. Heard whichever gateway the app or the desk sent them to.
    async def _commands(self, call: str, heard: asyncio.Event) -> None:
        try:
            listener = await self.signal.subscribe(COMMANDS_CHANNEL.format(call=call))
        except ServiceUnavailable:
            logger.warning("call %s: its commands are not heard here, the signal is down", call)
            return
        finally:
            heard.set()
        try:
            async for data in listener:
                await self._apply(call, Command.model_validate_json(data))
        finally:
            listener.close()

    async def _apply(self, call: str, command: Command) -> None:
        served = self.calls.get(call)
        if served is None or served.agent != command.agent:
            return
        if served.running is None:
            served.commands.put_nowait(command)
        elif command.type == SUPERVISOR_VERB:
            await served.running.supervise(SupervisorVerb.model_validate(command.data))
        else:
            model = command_of(command)
            declare_for_the_call(served, model)
            await served.running.apply(model)

    def _running_here(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for served in self.calls.values():
            if served.opened_here:
                named = f"{served.scope.org}|{served.scope.env.value}"
                counts[named] = counts.get(named, 0) + 1
        return counts

    def _say_sockets(self) -> None:
        self.elsewhere.shared.put(
            tuple(SocketRow(app.app, app.scope, app.address, app.connected_at, app.host) for app in self.apps.values())
        )

    def _stop(self, app: registry.SocketId) -> Callable[[str], Awaitable[None]]:
        async def stop(why: str) -> None:
            await tell_app(self.signal, app, ForApp(stop=why))

        return stop

    async def _answer_from_there(self, ask_id: str, answer: asyncio.Future[DevAnswer], heard: asyncio.Event) -> None:
        try:
            listener = await self.signal.subscribe(ANSWER_CHANNEL.format(id=ask_id))
        except ServiceUnavailable:
            return
        finally:
            heard.set()
        try:
            async for data in listener:
                if not answer.done():
                    answer.set_result(DevAnswer.model_validate_json(data))
                return
        finally:
            listener.close()

    def _stop_pump(self, call: str) -> None:
        pump_task = self.pumps.pop(call, None)
        if pump_task is not None:
            pump_task.cancel()


def declare_for_the_call(served: Served, model: WireModel) -> None:
    """A written call's own declaration of what is private, as the app configured it."""
    privacy = served.log.privacy
    if isinstance(model, SessionConfigure) and model.config is not None and privacy is not None:
        served.log.privacy = replace(privacy, config=declared.with_app_fields(privacy.config, model.config))
