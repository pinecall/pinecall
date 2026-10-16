"""One agent from the app's side: its registration, its tools' runs, a console's asks."""

import asyncio
import inspect
import time
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING, TypeVar

from pinecall._calls import Call, CallBook
from pinecall._listeners import AnyListener, Listener, Listeners
from pinecall.errors import DevRefused, NotConnected, Refused
from pinecall.wire._names import JsonObject
from pinecall.wire.commands import (
    AgentConfigure,
    AgentDrain,
    AgentRegister,
    DevAnswer,
    DevRefusal,
    Ping,
)
from pinecall.wire.events import (
    EVENTS,
    AgentConfigured,
    AgentDraining,
    AgentRegistered,
    DevRequest,
    ErrorEvent,
    event_of,
)
from pinecall.wire.events_turn import ToolCall
from pinecall.wire.frames import Entry, WireModel
from pinecall.wire.parts import AgentConfig, DevVerb, ToolResult, ToolSpec

if TYPE_CHECKING:
    from pinecall.client import Client

_E = TypeVar("_E", bound=WireModel)

ANSWER_WITHIN_S = 10.0

NO_DEV_HANDLER = (
    "this process answers no dev verbs: it is not a `pinecall start` in the agent's directory"
)

# What runs a tool: the model's arguments and the call, answered with the output.
Run = Callable[[JsonObject, Call], object]

# What answers a console's ask: the verb and its data, answered with the result.
DevHandler = Callable[[DevVerb, JsonObject], Awaitable[JsonObject] | JsonObject]


@dataclass(frozen=True)
class Tool:
    """A tool as the socket holds it: the spec the model reads, and what runs when it is called."""

    spec: ToolSpec
    run: Run


@dataclass(frozen=True)
class Role:
    """What a socket is for its agent: does it take calls that name no app; answer the console."""

    takes_unclaimed: bool = True
    answers_dev: bool = False


@dataclass
class _Waiting:
    lands_as: str
    id: str
    answer: asyncio.Future[WireModel]


class AgentSocket:
    """An agent's registration on one socket, sent again on every reconnect.

    Many sockets may hold one agent; a call that names no app goes to the newest that takes
    unclaimed calls, which is what makes a rolling deploy serve as soon as the new process
    registers. `drain` before leaving hands the live calls over instead of cutting them.
    """

    def __init__(
        self,
        slug: str,
        client: "Client",
        config: AgentConfig,
        tools: Sequence[Tool] = (),
        role: Role = Role(),  # noqa: B008 - frozen, so one default is shared safely
    ) -> None:
        """An agent `slug` held on `client`'s socket, declaring `config` and `tools`."""
        self.slug = slug
        self._client = client
        self._tools = {tool.spec.name: tool for tool in tools}
        self.config = config.model_copy(update={"tools": [tool.spec for tool in tools]})
        self._role = role
        self.app: str | None = None
        """The app id the gateway minted for this socket on its last registration."""
        self.calls = CallBook(self.command, client.on_error)
        self._listeners: Listeners[Call | None] = Listeners(client.on_error)
        self._waiting: list[_Waiting] = []
        self._running: set[asyncio.Task[None]] = set()
        self._asks: set[asyncio.Task[None]] = set()
        self._dev: DevHandler | None = None

    def on(self, type_: str, listener: Listener[Call | None]) -> Callable[[], None]:
        """Listen for one type of event across the agent's calls; None for its own log."""
        return self._listeners.on(type_, listener)

    def on_any(self, listener: AnyListener[Call | None]) -> Callable[[], None]:
        """Listen for every event of the agent."""
        return self._listeners.on_any(listener)

    def on_dev(self, handler: DevHandler) -> None:
        """Answer a console's asks; raise `DevRefused` to refuse one with a status."""
        self._dev = handler

    async def open(self) -> None:
        """Register, then declare the agent; on every (re)connect."""
        asked: dict[str, object] = {
            "routes": [],
            "sdk": self._client.sdk,
            "host": self._client.host,
        }
        asked |= {"takes_unclaimed": self._role.takes_unclaimed}
        asked |= {"answers_dev": True} if self._role.answers_dev else {}
        registered = await self._ask(
            "agent.register", AgentRegister.model_validate(asked), AgentRegistered
        )
        self.app = registered.app
        # A registration inherits the newest holder's declaration; one sent from here replaces it.
        if not self._role.answers_dev:
            await self.configure()

    async def configure(self, changes: Mapping[str, object] | None = None) -> AgentConfigured:
        """Send the declaration, with these fields changed; live calls keep their session."""
        if changes:
            self.config = self.config.model_copy(update=dict(changes))
        return await self._ask(
            "agent.configure", AgentConfigure(config=self.config), AgentConfigured
        )

    async def drain(self, within_s: float = ANSWER_WITHIN_S) -> AgentDraining:
        """Take no new call, and hand the live ones to another holder or park them for the next."""
        return await self._ask("agent.drain", AgentDrain(), AgentDraining, within_s)

    @property
    def in_flight(self) -> int:
        """How many tool runs have not sent their result yet."""
        return len(self._running)

    async def settled(self) -> None:
        """Return once every running tool has sent its result."""
        await asyncio.gather(*self._running, return_exceptions=True)

    def ping(self) -> None:
        """Ask whether the socket is alive; the gateway answers `pong`."""
        self.command("ping", None, Ping())

    def command(self, type_: str, call: str | None, data: WireModel) -> None:
        """Send one command on the agent's behalf."""
        self._client.send(type_, self.slug, call, data, f"{self.slug}:{type_}")

    # ── the socket's side ──

    def take(self, entry: Entry) -> None:
        """Fold one entry into its call and hand it to the listeners; a tool call or an ask runs."""
        event = event_of(entry)
        call = None if entry.call is None else self.calls.of(entry.call, entry.ts)
        self._settle(entry.type, event)
        if call is not None:
            call.take(entry.type, event)
        self._listeners.emit(entry.type, event, call)
        self._client.seen(entry.type, event, call)
        if isinstance(event, DevRequest):
            self._spawn(self._answer(event), self._asks)
        elif isinstance(event, ToolCall) and call is not None:
            self._spawn(self._ran(event, call), self._running)
        if call is not None:
            self.calls.forget(call)

    # Every outcome is exactly one tool.result: a turn that never gets one waits forever.
    async def _ran(self, asked: ToolCall, call: Call) -> None:
        tool = self._tools.get(asked.name)
        started = time.monotonic()
        answer = {"call_id": asked.call_id, "name": asked.name}
        if tool is None:
            call.tool_result(
                ToolResult.model_validate(
                    answer | {"error": f"this app declares no tool called {asked.name}"}
                )
            )
            return
        try:
            output = tool.run(asked.arguments, call)
            if inspect.isawaitable(output):
                output = await output
            answer |= {"output": output}
        except Exception as failed:  # noqa: BLE001 - what the tool raised is its answer, for the model
            answer |= {"error": str(failed) or type(failed).__name__}
        answer |= {"duration_s": time.monotonic() - started}
        try:
            call.tool_result(ToolResult.model_validate(answer))
        except Exception as unsent:  # noqa: BLE001 - the socket dropped; said, never raised into the loop
            self._client.on_error(unsent)

    # Every ask gets one dev.answer, or the console's request hangs until the gateway gives up.
    async def _answer(self, asked: DevRequest) -> None:
        if self._dev is None:
            refused = DevRefusal(status=501, detail=NO_DEV_HANDLER)
            self.command("dev.answer", None, DevAnswer(id=asked.id, refused=refused))
            return
        try:
            result = self._dev(asked.verb, asked.data)
            if inspect.isawaitable(result):
                result = await result
            answer = DevAnswer(id=asked.id, result=result)
        except DevRefused as refused:
            answer = DevAnswer(
                id=asked.id, refused=DevRefusal(status=refused.status, detail=refused.detail)
            )
        except Exception as failed:  # noqa: BLE001 - the console is told, and the process goes on
            answer = DevAnswer(id=asked.id, refused=DevRefusal(status=500, detail=str(failed)))
        self.command("dev.answer", None, answer)

    # ── waiting for an answer ──

    async def _ask(
        self, type_: str, data: WireModel, lands_as: type[_E], within_s: float = ANSWER_WITHIN_S
    ) -> _E:
        """Send a command and wait for the event it lands as, or an `error` carrying its id."""
        waiting = _Waiting(
            event_type_of(lands_as),
            f"{self.slug}:{type_}",
            asyncio.get_running_loop().create_future(),
        )
        self._waiting.append(waiting)
        try:
            self.command(type_, None, data)
            landed = await asyncio.wait_for(waiting.answer, within_s)
        except TimeoutError:
            raise NotConnected(f"{type_}: the gateway did not answer in {within_s:g}s") from None
        finally:
            self._waiting.remove(waiting)
        if not isinstance(landed, lands_as):
            raise NotConnected(f"{type_}: the gateway answered with {type(landed).__name__}")
        return landed

    def _settle(self, type_: str, event: WireModel) -> None:
        for waiting in list(self._waiting):
            if waiting.answer.done():
                continue
            if type_ == waiting.lands_as:
                waiting.answer.set_result(event)
            elif isinstance(event, ErrorEvent) and event.id == waiting.id:
                waiting.answer.set_exception(Refused(event.code, event.message))

    def _spawn(self, work: Awaitable[None], kept: set[asyncio.Task[None]]) -> None:
        task = asyncio.ensure_future(work)
        kept.add(task)
        task.add_done_callback(kept.discard)


def event_type_of(model: type[WireModel]) -> str:
    """The wire's name for an event model."""
    return next(name for name, one in EVENTS.items() if one is model)
